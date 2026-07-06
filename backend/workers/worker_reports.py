import asyncio
import logging
from datetime import datetime
from backend.workers.base import BaseWorker
from backend.models.base import AsyncSessionLocal
from backend.models.report import TendencyReport
from backend.models.event import Event
from backend.services.tendency_engine import run_tendency_engine
from backend.services.report_writer import generate_prose_sections
from backend.services.encryption import encrypt_json
from backend.services.agent_log import log_agent_action, confidence_band
from sqlalchemy import select, update, or_
from sqlalchemy.dialects.postgresql import array

logger = logging.getLogger(__name__)

class ReportsWorker(BaseWorker):
    job_type = "report"

    async def handle(self, payload: dict) -> dict:
        report_id = payload["report_id"]
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(TendencyReport).where(TendencyReport.id == report_id))
            report = result.scalar_one_or_none()
            if not report:
                raise ValueError(f"Report {report_id} not found")

            events_result = await db.execute(
                select(Event).where(Event.game_id.in_(report.game_ids))
            )
            events = events_result.scalars().all()

        tendency_summary = await run_tendency_engine(report.sport, events)
        prose_sections = await generate_prose_sections(
            sport=report.sport,
            tendency_summary=tendency_summary,
            report_type=report.report_type,
            is_trial=report.is_trial,
        )
        encrypted = encrypt_json(tendency_summary)

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
            detail={"report_id": str(report_id), "sections": len(prose_sections), "events": len(events)},
        )

        async with AsyncSessionLocal() as db:
            await db.execute(update(TendencyReport).where(TendencyReport.id == report_id).values(
                summary_json=encrypted,
                prose_sections=prose_sections,
                generated_at=datetime.utcnow(),
            ))
            await db.commit()

        return {"report_id": report_id, "sections": len(prose_sections)}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(ReportsWorker().run_forever())
