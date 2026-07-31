"""
Per-account learning loop — coach controls (Engine §14).

Everything here is scoped to the caller's organization. A coach sees their own
label-quality score, reviews the adjustments the loop proposes from their
corrections, accepts/rejects/resets each one, toggles Manual Mode, and exports
their full correction history. Nothing reads or writes another account's data.
"""
import csv
import io
import logging
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel

from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.learning import (
    CoachLabelCorrection, AccountLearningAdjustment, LabelQualityScore,
)
from backend.services.auth import get_current_user, get_current_org

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/learning", tags=["learning"])


def _adj_out(a: AccountLearningAdjustment) -> dict:
    return {
        "id": str(a.id), "sport": a.sport, "field": a.field,
        "from_value": a.from_value, "to_value": a.to_value,
        "support_count": a.support_count, "status": a.status, "note": a.note,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


@router.get("/summary")
async def learning_summary(user: User = Depends(get_current_user),
                           org: Organization = Depends(get_current_org),
                           db: AsyncSession = Depends(get_db)):
    """The account's label-quality score, Manual Mode state, and adjustment counts."""
    score = (await db.execute(
        select(LabelQualityScore).where(LabelQualityScore.organization_id == org.id)
    )).scalar_one_or_none()

    adjustments = (await db.execute(
        select(AccountLearningAdjustment).where(
            AccountLearningAdjustment.organization_id == org.id)
    )).scalars().all()
    counts = {"pending": 0, "active": 0, "rejected": 0}
    for a in adjustments:
        counts[a.status] = counts.get(a.status, 0) + 1

    return {
        "manual_mode": bool(org.learning_loop_manual),
        "score": {
            "total_corrections": getattr(score, "total_corrections", 0) or 0,
            "high": getattr(score, "high_count", 0) or 0,
            "low": getattr(score, "low_count", 0) or 0,
            "reclass": getattr(score, "reclass_count", 0) or 0,
            "systematic": getattr(score, "systematic_count", 0) or 0,
        },
        "adjustments": counts,
    }


@router.get("/adjustments")
async def list_adjustments(status: str = None,
                           user: User = Depends(get_current_user),
                           org: Organization = Depends(get_current_org),
                           db: AsyncSession = Depends(get_db)):
    """Proposed / active / rejected adjustments for this account (newest first)."""
    q = select(AccountLearningAdjustment).where(
        AccountLearningAdjustment.organization_id == org.id)
    if status in ("pending", "active", "rejected"):
        q = q.where(AccountLearningAdjustment.status == status)
    q = q.order_by(AccountLearningAdjustment.updated_at.desc())
    rows = (await db.execute(q)).scalars().all()
    return {"adjustments": [_adj_out(a) for a in rows]}


async def _load_owned_adjustment(adjustment_id: str, org_id, db) -> AccountLearningAdjustment:
    a = (await db.execute(select(AccountLearningAdjustment).where(
        AccountLearningAdjustment.id == adjustment_id,
        AccountLearningAdjustment.organization_id == org_id,
    ))).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Adjustment not found")
    return a


@router.post("/adjustments/{adjustment_id}/accept")
async def accept_adjustment(adjustment_id: str,
                            user: User = Depends(get_current_user),
                            org: Organization = Depends(get_current_org),
                            db: AsyncSession = Depends(get_db)):
    """Activate an adjustment — it will relabel matching plays in future reports."""
    a = await _load_owned_adjustment(adjustment_id, org.id, db)
    a.status = "active"
    a.activated_by = user.id
    await db.commit()
    return {"ok": True, "adjustment": _adj_out(a)}


@router.post("/adjustments/{adjustment_id}/reject")
async def reject_adjustment(adjustment_id: str,
                            user: User = Depends(get_current_user),
                            org: Organization = Depends(get_current_org),
                            db: AsyncSession = Depends(get_db)):
    """Reject an adjustment — it stays rejected (won't re-propose) until reset."""
    a = await _load_owned_adjustment(adjustment_id, org.id, db)
    a.status = "rejected"
    await db.commit()
    return {"ok": True, "adjustment": _adj_out(a)}


@router.post("/adjustments/{adjustment_id}/reset")
async def reset_adjustment(adjustment_id: str,
                           user: User = Depends(get_current_user),
                           org: Organization = Depends(get_current_org),
                           db: AsyncSession = Depends(get_db)):
    """Reset a decision back to pending so the loop can re-evaluate it."""
    a = await _load_owned_adjustment(adjustment_id, org.id, db)
    a.status = "pending"
    a.activated_by = None
    await db.commit()
    return {"ok": True, "adjustment": _adj_out(a)}


class ManualMode(BaseModel):
    enabled: bool


@router.post("/manual-mode")
async def set_manual_mode(body: ManualMode,
                          user: User = Depends(get_current_user),
                          org: Organization = Depends(get_current_org),
                          db: AsyncSession = Depends(get_db)):
    """Opt in/out of the auto-loop. Corrections are still recorded either way;
    Manual Mode only stops proposing and applying adjustments."""
    await db.execute(update(Organization).where(Organization.id == org.id).values(
        learning_loop_manual=bool(body.enabled)))
    await db.commit()
    return {"ok": True, "manual_mode": bool(body.enabled)}


@router.get("/corrections/export")
async def export_corrections(user: User = Depends(get_current_user),
                             org: Organization = Depends(get_current_org),
                             db: AsyncSession = Depends(get_db)):
    """The account's full correction history as CSV (Settings > My Labeling History)."""
    rows = (await db.execute(
        select(CoachLabelCorrection)
        .where(CoachLabelCorrection.organization_id == org.id)
        .order_by(CoachLabelCorrection.created_at.desc())
    )).scalars().all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["created_at", "sport", "field", "category", "old_value", "new_value",
                "was_auto_detected", "ai_confidence", "signal"])
    for r in rows:
        w.writerow([
            r.created_at.isoformat() if r.created_at else "",
            r.sport or "", r.field or "", r.category or "",
            r.old_value or "", r.new_value or "",
            "yes" if r.was_auto_detected else "no",
            "" if r.ai_confidence is None else r.ai_confidence,
            r.signal or "",
        ])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="labeling-history.csv"'},
    )
