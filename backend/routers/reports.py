from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.report import TendencyReport
from backend.models.job import Job
from backend.services.auth import get_current_user, get_current_org
from backend.services.encryption import decrypt_json

router = APIRouter(prefix="/reports", tags=["reports"])

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
    return [{"id": str(r.id), "title": r.title, "sport": r.sport, "report_type": r.report_type, "is_trial": r.is_trial, "watermarked": r.watermarked, "generated_at": r.generated_at.isoformat() if r.generated_at else None} for r in reports]

@router.post("")
async def create_report(body: ReportCreate, user: User = Depends(get_current_user), org: Organization = Depends(get_current_org), db: AsyncSession = Depends(get_db)):
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
    return {
        "id": str(report.id),
        "title": report.title,
        "sport": report.sport,
        "report_type": report.report_type,
        "is_trial": report.is_trial,
        "watermarked": report.watermarked,
        "sections": report.prose_sections or [],
        "summary": summary,
        "generated_at": report.generated_at.isoformat() if report.generated_at else None,
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
