import asyncio
import logging
from datetime import datetime, timedelta
from backend.workers.base import BaseWorker
from backend.models.base import AsyncSessionLocal
from backend.models.report import TendencyReport
from backend.models.event import Event
from backend.services.tendency_engine import run_tendency_engine
from backend.services.report_writer import generate_prose_sections
from backend.services.coach_notes import collect_flagged_plays
from backend.services.report_failures import failure_reason, is_quota_error, dead_letter_reason
from backend.services.encryption import encrypt_json
from backend.services.agent_log import log_agent_action, confidence_band
from backend.services.email_service import send_report_failure_alert
from backend.config import settings
from sqlalchemy import select, update, func, or_
from sqlalchemy.dialects.postgresql import array

logger = logging.getLogger(__name__)

class ReportsWorker(BaseWorker):
    job_type = "report"
    # Report generation is short (2-5 min) and idempotent (a re-run overwrites the
    # report), so an orphaned run can be reclaimed fast without risk of a harmful
    # double-execution. Recovers in ~4-5 min instead of the base ~10.
    stuck_threshold_minutes = 4

    async def on_dead_letter(self, payload: dict, reason: str) -> None:
        """A report job that was given up on must not leave the report spinning: mark
        it failed (unless a run already succeeded or handle() already recorded why)."""
        report_id = payload.get("report_id")
        if not report_id:
            return
        async with AsyncSessionLocal() as db:
            r = await db.get(TendencyReport, report_id)
            if r is None:
                return
            new = dead_letter_reason(r.error_reason, r.generated_at, reason)
            if new and new != r.error_reason:
                r.error_reason = new
                await db.commit()

    async def handle(self, payload: dict) -> dict:
        report_id = payload["report_id"]
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(TendencyReport).where(TendencyReport.id == report_id))
            report = result.scalar_one_or_none()
            if not report:
                raise ValueError(f"Report {report_id} not found")
            org_id, title = report.organization_id, report.title
            sport, report_type, is_trial = report.sport, report.report_type, report.is_trial

            events_result = await db.execute(
                select(Event).where(Event.game_id.in_(report.game_ids))
            )
            events = events_result.scalars().all()

        try:
            tendency_summary = await run_tendency_engine(sport, events)
            # Fold the coach's own starred plays + notes into the report context so their
            # first-hand reads surface in the generated report (not lost in aggregation).
            flagged = collect_flagged_plays(events)
            if flagged:
                tendency_summary["coach_flagged_plays"] = flagged
            prose_sections = await generate_prose_sections(
                sport=sport,
                tendency_summary=tendency_summary,
                report_type=report_type,
                is_trial=is_trial,
            )
            encrypted = encrypt_json(tendency_summary)
        except Exception as e:
            # Record the failure on the report so the UI stops spinning and offers a
            # retry, and alert the founder on a usage/limit-class failure. A hard quota
            # limit is NOT retried (a retry won't lift it); other errors re-raise so the
            # base worker's attempt counter + circuit breaker still apply.
            await self._mark_failed(report_id, org_id, title, e)
            if is_quota_error(failure_reason(e)):
                return {"report_id": report_id, "status": "failed"}
            raise

        # UATP: log the scouting agent's action with its data-confidence band so
        # coaches can audit how strongly to trust this report (identity + reason +
        # confidence). Best-effort; never blocks report generation.
        conf = (tendency_summary.get("data_confidence") or {}).get("avg_confidence")
        scouting = tendency_summary.get("scouting") or {}
        # Basketball uses game_plan_priorities[].adjustment; football uses
        # head_coach_priorities[].call. Support both shapes for the audit line.
        bball_gp = scouting.get("game_plan_priorities") or []
        fball_gp = scouting.get("head_coach_priorities") or []
        if bball_gp:
            top_priority = bball_gp[0].get("adjustment", "n/a")
        elif fball_gp:
            top_priority = fball_gp[0].get("call", "n/a")
        else:
            top_priority = "n/a"
        await log_agent_action(
            action="generate_scouting_report",
            organization_id=str(report.organization_id),
            phase="scout",
            reason=(
                f"Generated {len(prose_sections)}-section {report.sport} scouting report from "
                f"{len(events)} events. Confidence band: {confidence_band(conf)}. "
                f"Top game-plan priority: {top_priority}"
            ),
            confidence=conf,
            level="success",
            detail={"report_id": str(report_id), "sections": len(prose_sections),
                    "events": len(events), "coach_flagged_plays": len(flagged)},
        )

        async with AsyncSessionLocal() as db:
            await db.execute(update(TendencyReport).where(TendencyReport.id == report_id).values(
                summary_json=encrypted,
                prose_sections=prose_sections,
                generated_at=datetime.utcnow(),
                error_reason=None,   # clear any prior failure on a successful (re)generation
            ))
            await db.commit()

        return {"report_id": report_id, "sections": len(prose_sections)}

    async def _mark_failed(self, report_id, org_id, title, exc):
        """Write the real failure reason onto the report (founder/admin-facing) and,
        for a usage/limit-class failure, alert the founder once (deduped)."""
        reason = failure_reason(exc)
        already_quota = False
        async with AsyncSessionLocal() as db:
            r = await db.get(TendencyReport, report_id)
            if r is not None:
                already_quota = is_quota_error(r.error_reason or "")
                r.error_reason = reason
                await db.commit()
        logger.error(f"[report] {report_id} generation failed: {reason}")
        # Alert the founder only for the quota/limit class, and not again for a retry of
        # the same already-flagged report.
        if is_quota_error(reason) and not already_quota:
            await self._alert_founder(org_id, report_id, title, reason)

    async def _alert_founder(self, org_id, report_id, title, reason):
        to = (settings.ADMIN_EMAILS or "").split(",")[0].strip()
        if not to:
            return
        try:
            # Cross-report dedup: at most one alert per org per hour during an outage,
            # so a burst of coaches hitting the limit doesn't flood the founder inbox.
            async with AsyncSessionLocal() as db:
                cutoff = datetime.utcnow() - timedelta(hours=1)
                recent = (await db.execute(
                    select(func.count()).select_from(TendencyReport).where(
                        TendencyReport.organization_id == org_id,
                        TendencyReport.id != report_id,
                        TendencyReport.error_reason.isnot(None),
                        TendencyReport.updated_at >= cutoff,
                    ))).scalar() or 0
            if recent:
                return
            await send_report_failure_alert(to, title, reason)
        except Exception as e:
            logger.error(f"[report] founder failure-alert not sent: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(ReportsWorker().run_forever())
