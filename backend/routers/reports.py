from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import secrets
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.report import TendencyReport
from backend.models.report_chat import ReportChatMessage
from backend.models.event import Event
from backend.models.game import Game
from backend.models.job import Job
from backend.services.auth import get_current_user, get_current_org
from backend.services.entitlements import assert_feature_allowed
from backend.services.encryption import decrypt_json
from backend.services.report_failures import report_status, CLIENT_FAILURE_MESSAGE
from backend.utils.timeutils import to_naive_utc

router = APIRouter(prefix="/reports", tags=["reports"])

SHARE_DEFAULT_DAYS = 7
SHARE_MAX_DAYS = 30


def clamp_share_days(days) -> int:
    """Share links live 7 days by default, 30 max. Anything unparseable -> default."""
    try:
        d = int(days)
    except (TypeError, ValueError):
        d = SHARE_DEFAULT_DAYS
    return max(1, min(SHARE_MAX_DAYS, d))

class ReportCreate(BaseModel):
    title: str
    sport: str
    game_ids: List[str]
    team_id: Optional[str] = None
    report_type: str = "opponent"

@router.get("")
async def list_reports(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TendencyReport).where(TendencyReport.organization_id == user.organization_id).order_by(TendencyReport.created_at.desc()))
    reports = result.scalars().all()
    return [{"id": str(r.id), "title": r.title, "sport": r.sport, "report_type": r.report_type, "is_trial": r.is_trial, "watermarked": r.watermarked, "generated_at": r.generated_at.isoformat() if r.generated_at else None, "status": report_status(r.generated_at, r.error_reason)} for r in reports]

@router.post("")
async def create_report(body: ReportCreate, user: User = Depends(get_current_user), org: Organization = Depends(get_current_org), db: AsyncSession = Depends(get_db)):
    # Entitlements: combining more than one game into a report is a paid feature.
    if len(body.game_ids or []) > 1:
        assert_feature_allowed(org, "multi_game_reports")
    report = TendencyReport(
        organization_id=org.id,
        team_id=body.team_id,
        game_ids=body.game_ids,
        sport=body.sport,
        report_type=body.report_type,
        title=body.title,
        is_trial=org.is_trial,
        watermarked=org.is_trial,
    )
    db.add(report)
    await db.flush()
    job = Job(organization_id=org.id, job_type="report", payload={"report_id": str(report.id)})
    db.add(job)
    await db.commit()
    return {"id": str(report.id), "status": "queued"}

@router.get("/{report_id}")
async def get_report(report_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TendencyReport).where(TendencyReport.id == report_id, TendencyReport.organization_id == user.organization_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    summary = None
    if report.summary_json:
        try:
            summary = decrypt_json(report.summary_json)
        except Exception:
            pass

    sections = report.prose_sections or []
    # Recover a report whose sections are a raw-JSON dump (a past parse failure).
    # Re-parse with the tolerant parser and persist the fix so it's permanent.
    if len(sections) == 1 and isinstance(sections[0], dict):
        body = sections[0].get("body") or ""
        if '"heading"' in body and '"insight_type"' in body:
            from backend.services.report_writer import _parse_report_sections
            recovered = _parse_report_sections(body)
            if len(recovered) > 1 or (recovered and recovered[0].get("heading") != "Tendency Analysis"):
                sections = recovered
                report.prose_sections = recovered
                await db.commit()

    # Film resolution honesty (migration 021): the lowest-res source game caps how
    # well jerseys and the down/distance score-bug can be read. Surface it so the UI
    # can warn the coach a report is resolution-limited. None when unknown (older
    # films predating resolution logging); we never warn without data.
    film_min_height = None
    low_res_film = False
    if report.game_ids:
        hres = await db.execute(select(Game.film_height).where(
            Game.id.in_(report.game_ids),
            Game.organization_id == user.organization_id,
            Game.film_height.isnot(None),
        ))
        heights = [h for h in hres.scalars().all() if h]
        if heights:
            film_min_height = min(heights)
            low_res_film = film_min_height < 480

    return {
        "id": str(report.id),
        "title": report.title,
        "sport": report.sport,
        "report_type": report.report_type,
        "is_trial": report.is_trial,
        "watermarked": report.watermarked,
        "sections": sections,
        "summary": summary,
        "film_min_height": film_min_height,
        "low_res_film": low_res_film,
        "generated_at": report.generated_at.isoformat() if report.generated_at else None,
        # status = ready | failed | generating. On failure the coach sees only a generic
        # message; the real reason (error_reason) stays server-side for the founder.
        "status": report_status(report.generated_at, report.error_reason),
        "message": (CLIENT_FAILURE_MESSAGE if (report.error_reason and not report.generated_at) else None),
    }


@router.post("/{report_id}/retry")
async def retry_report(report_id: str, user: User = Depends(get_current_user),
                       org: Organization = Depends(get_current_org), db: AsyncSession = Depends(get_db)):
    """Re-queue a failed report generation (clears the failure and enqueues a fresh
    job). Only meaningful for a report that failed and hasn't since generated."""
    result = await db.execute(select(TendencyReport).where(
        TendencyReport.id == report_id, TendencyReport.organization_id == user.organization_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.generated_at:
        return {"ok": True, "status": "ready"}  # already done, nothing to retry
    report.error_reason = None
    # Re-analysis resets the report-scoped chat (Engine §13): the film is being
    # re-read, so prior answers no longer describe what the report will say.
    await db.execute(delete(ReportChatMessage).where(
        ReportChatMessage.report_id == report.id,
        ReportChatMessage.organization_id == user.organization_id,
    ))
    db.add(Job(organization_id=org.id, job_type="report", payload={"report_id": str(report.id)}))
    await db.commit()
    return {"ok": True, "status": "generating"}


@router.get("/{report_id}/export")
async def export_report(
    report_id: str,
    format: str = "coordinator",         # coordinator|position|head_coach|player
    unit: Optional[str] = None,          # position format: OL|DL|WR|DB|QB|LB|RB|ST
    player: Optional[str] = None,        # player format: a jersey number
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reshape a generated report into one of the four Module-9 formats, returned
    as normalized blocks the frontend renders and prints (Save as PDF)."""
    from backend.services.report_export import build_export, EXPORT_FORMATS

    if format not in EXPORT_FORMATS:
        raise HTTPException(status_code=422,
                            detail=f"format must be one of: {', '.join(EXPORT_FORMATS)}")

    result = await db.execute(select(TendencyReport).where(
        TendencyReport.id == report_id, TendencyReport.organization_id == user.organization_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if not report.generated_at:
        raise HTTPException(status_code=409, detail="Report is still generating.")

    summary = None
    if report.summary_json:
        try:
            summary = decrypt_json(report.summary_json)
        except Exception:
            summary = None

    payload = build_export(
        {
            "title": report.title,
            "sport": report.sport,
            "report_type": report.report_type,
            "sections": report.prose_sections or [],
            "summary": summary,
            "watermarked": report.watermarked,
            "generated_at": report.generated_at.isoformat() if report.generated_at else None,
        },
        fmt=format, unit=unit, player=player,
    )
    return payload


@router.get("/{report_id}/export/csv")
async def export_report_csv(
    report_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every tagged play in this report's games as a flat CSV (one row per play).
    Columns are the stable report_export.CSV_COLUMNS contract."""
    from backend.services.report_export import plays_to_csv

    result = await db.execute(select(TendencyReport).where(
        TendencyReport.id == report_id, TendencyReport.organization_id == user.organization_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    game_ids = report.game_ids or []
    events = []
    if game_ids:
        ev = await db.execute(
            select(Event)
            .where(
                Event.game_id.in_(game_ids),
                Event.organization_id == user.organization_id,   # defense in depth
                Event.event_type != "scout_meta",
            )
            .order_by(Event.game_id, Event.time_seconds.asc())
        )
        events = ev.scalars().all()

    csv_text = plays_to_csv(events)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="report-{report_id}-plays.csv"'},
    )


@router.post("/{report_id}/share")
async def create_report_share(
    report_id: str,
    expires_in_days: int = SHARE_DEFAULT_DAYS,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enable (or extend) a read-only public share link for this report. Returns a
    capability token; the link expires in `expires_in_days` (7 default, 30 max)."""
    result = await db.execute(select(TendencyReport).where(
        TendencyReport.id == report_id, TendencyReport.organization_id == user.organization_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    days = clamp_share_days(expires_in_days)
    if not report.share_token:
        report.share_token = secrets.token_urlsafe(24)
    report.share_expires_at = datetime.utcnow() + timedelta(days=days)
    report.share_view_count = report.share_view_count or 0
    await db.commit()
    return {
        "share_token": report.share_token,
        "expires_at": report.share_expires_at.isoformat(),
        "expires_in_days": days,
        # Path the frontend renders as the public, no-login share page.
        "share_path": f"/reports/{report_id}/share/{report.share_token}",
    }


@router.delete("/{report_id}/share")
async def revoke_report_share(
    report_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Immediately kill the public share link for this report."""
    result = await db.execute(select(TendencyReport).where(
        TendencyReport.id == report_id, TendencyReport.organization_id == user.organization_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    report.share_token = None
    report.share_expires_at = None
    await db.commit()
    return {"ok": True, "message": "Share link revoked."}


@router.get("/{report_id}/share/{token}")
async def view_shared_report(report_id: str, token: str, db: AsyncSession = Depends(get_db)):
    """Public, no-login, read-only view of a shared report. Gated by the capability
    token and its expiry. No player names appear in a report payload (jersey numbers
    and tendencies only), so nothing identifiable is exposed here."""
    result = await db.execute(select(TendencyReport).where(
        TendencyReport.id == report_id, TendencyReport.share_token == token))
    report = result.scalar_one_or_none()
    if not report or not report.share_token:
        raise HTTPException(status_code=404, detail="This share link is invalid.")
    if not report.share_expires_at or datetime.utcnow() > to_naive_utc(report.share_expires_at):
        raise HTTPException(status_code=410, detail="This share link has expired.")

    await db.execute(update(TendencyReport).where(TendencyReport.id == report.id).values(
        share_view_count=TendencyReport.share_view_count + 1))
    await db.commit()

    summary = None
    if report.summary_json:
        try:
            summary = decrypt_json(report.summary_json)
        except Exception:
            summary = None
    # The coach's own notes are free text that may name players; the public, no-login
    # view is jersey/tendency only, so drop the coach's-notes section and the raw
    # flagged-play data from the shared payload (keeps the "no player names" guarantee).
    public_sections = [s for s in (report.prose_sections or [])
                       if (s or {}).get("insight_type") != "coach_notes"]
    if isinstance(summary, dict):
        summary = {k: v for k, v in summary.items() if k != "coach_flagged_plays"}
    return {
        "id": str(report.id),
        "title": report.title,
        "sport": report.sport,
        "report_type": report.report_type,
        "watermarked": report.watermarked,
        "sections": public_sections,
        "summary": summary,
        "generated_at": report.generated_at.isoformat() if report.generated_at else None,
        "shared": True,
    }


@router.delete("/{report_id}")
async def delete_report(report_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TendencyReport).where(TendencyReport.id == report_id, TendencyReport.organization_id == user.organization_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    await db.delete(report)
    await db.commit()
    return {"ok": True}
