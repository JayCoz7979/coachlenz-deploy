"""
Athletic Department usage dashboard (Track 3.1). A subscription feature of the
athletic_dept / district tiers: an AD sees usage by coach / sport / type, sets a
per-coach monthly analysis cap, and exports a usage CSV. Enforcement of the caps
lives on the analysis trigger (ai_detect); this router is the visibility + control.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.usage import AnalysisUsage, CoachUsageLimit
from backend.services.auth import get_current_user, get_current_org
from backend.services.usage import aggregate_usage, usage_to_csv, month_start

router = APIRouter(prefix="/ad", tags=["ad"])

AD_ACCOUNT_TIERS = {"athletic_dept", "district"}


async def require_ad_account(org: Organization = Depends(get_current_org)) -> Organization:
    if (org.subscription_tier or "").strip().lower() not in AD_ACCOUNT_TIERS:
        raise HTTPException(status_code=403,
                            detail="The usage dashboard is available on Athletic Dept and District plans.")
    return org


def _parse_range(frm: Optional[str], to: Optional[str]):
    now = datetime.utcnow()
    try:
        start = datetime.fromisoformat(frm) if frm else month_start(now)
        end = datetime.fromisoformat(to) if to else now
    except ValueError:
        raise HTTPException(status_code=422, detail="from/to must be ISO dates (YYYY-MM-DD).")
    return start, end


async def _usage_rows(db, org_id, start, end):
    res = await db.execute(select(AnalysisUsage).where(
        AnalysisUsage.organization_id == org_id,
        AnalysisUsage.created_at >= start, AnalysisUsage.created_at <= end,
    ).order_by(AnalysisUsage.created_at))
    return res.scalars().all()


async def _org_users(db, org_id):
    res = await db.execute(select(User).where(User.organization_id == org_id))
    return res.scalars().all()


async def _limits(db, org_id):
    res = await db.execute(select(CoachUsageLimit).where(CoachUsageLimit.organization_id == org_id))
    return {str(l.user_id): l.monthly_run_limit for l in res.scalars().all()}


@router.get("/usage")
async def ad_usage(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    org: Organization = Depends(require_ad_account),
    db: AsyncSession = Depends(get_db),
):
    start, end = _parse_range(from_, to)
    rows = await _usage_rows(db, org.id, start, end)
    agg = aggregate_usage(rows)

    # This month's per-coach counts drive the "remaining vs cap" figures.
    ms = month_start(datetime.utcnow())
    month_rows = await _usage_rows(db, org.id, ms, datetime.utcnow())
    month_by_coach = aggregate_usage(month_rows)["by_coach"]

    users = await _org_users(db, org.id)
    limits = await _limits(db, org.id)
    coaches = []
    for u in users:
        uid = str(u.id)
        lim = limits.get(uid)
        used_month = month_by_coach.get(uid, 0)
        coaches.append({
            "user_id": uid, "name": u.name, "email": u.email, "role": u.role,
            "runs_in_range": agg["by_coach"].get(uid, 0),
            "runs_this_month": used_month,
            "monthly_limit": lim,
            "remaining": (None if not lim or lim <= 0 else max(0, lim - used_month)),
        })
    coaches.sort(key=lambda c: c["runs_in_range"], reverse=True)
    return {
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "total_runs": agg["total"], "by_sport": agg["by_sport"], "by_type": agg["by_type"],
        "coaches": coaches,
    }


@router.get("/usage/export")
async def ad_usage_export(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    org: Organization = Depends(require_ad_account),
    db: AsyncSession = Depends(get_db),
):
    start, end = _parse_range(from_, to)
    rows = await _usage_rows(db, org.id, start, end)
    names = {str(u.id): (u.name, u.email) for u in await _org_users(db, org.id)}
    flat = [{
        "coach": names.get(str(r.user_id), ("", ""))[0],
        "email": names.get(str(r.user_id), ("", ""))[1],
        "sport": r.sport, "analysis_type": r.analysis_type, "timestamp": r.created_at,
    } for r in rows]
    return Response(
        content=usage_to_csv(flat),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="coachlenz-usage.csv"'},
    )


class LimitIn(BaseModel):
    user_id: str
    monthly_run_limit: int


@router.get("/limits")
async def list_limits(org: Organization = Depends(require_ad_account), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(CoachUsageLimit).where(CoachUsageLimit.organization_id == org.id))
    return [{"user_id": str(l.user_id), "monthly_run_limit": l.monthly_run_limit} for l in res.scalars().all()]


@router.post("/limits")
async def set_limit(body: LimitIn, org: Organization = Depends(require_ad_account), db: AsyncSession = Depends(get_db)):
    # The coach must belong to this org.
    ures = await db.execute(select(User).where(
        User.id == body.user_id, User.organization_id == org.id))
    if not ures.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Coach not found in your organization.")
    if body.monthly_run_limit < 0:
        raise HTTPException(status_code=422, detail="monthly_run_limit must be >= 0 (0 = unlimited).")

    res = await db.execute(select(CoachUsageLimit).where(
        CoachUsageLimit.organization_id == org.id, CoachUsageLimit.user_id == body.user_id))
    limit = res.scalar_one_or_none()
    if limit:
        limit.monthly_run_limit = body.monthly_run_limit
    else:
        db.add(CoachUsageLimit(organization_id=org.id, user_id=body.user_id,
                               monthly_run_limit=body.monthly_run_limit))
    await db.commit()
    return {"ok": True, "user_id": body.user_id, "monthly_run_limit": body.monthly_run_limit}
