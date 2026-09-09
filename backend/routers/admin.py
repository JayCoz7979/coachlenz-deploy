from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from pydantic import BaseModel
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.abuse import RiskFlag, AuditLog
from backend.models.teams_of_month import TeamSubmission, FeaturedTeam
from backend.models.usage import AnalysisUsage
from backend.models.funnel import FunnelEvent
from backend.models.agent_log import AgentLog
from backend.models.game import Game
from backend.services.auth import require_admin
from backend.services import feature_flags, retention, funnel, credits, detection_quality
from datetime import datetime

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/feature-flags")
async def get_feature_flags(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Every togglable feature with its current effective state (override or default)."""
    return {"flags": await feature_flags.list_flags(db)}


class FlagUpdate(BaseModel):
    enabled: bool


@router.put("/feature-flags/{key}")
async def set_feature_flag(key: str, body: FlagUpdate, user: User = Depends(require_admin),
                           db: AsyncSession = Depends(get_db)):
    """Toggle a feature at runtime (no redeploy). Writes a DB override of the env default."""
    try:
        await feature_flags.set_flag(db, key, body.enabled, user.id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown feature flag")
    return {"ok": True, "key": key, "enabled": body.enabled}

@router.get("/retention")
async def retention_gate(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """The retention gate: per-cohort activation + return, derived from real signup
    and delivered-analysis events. This is the number that decides whether the
    product may build feature breadth (see BUILD_STATUS.md). Founder-readable only.

    Kept separate from the Athletic Dept usage dashboard: same events, different
    question. No new table, so nothing here can drift from or fake the truth."""
    orgs = (await db.execute(select(Organization.id, Organization.created_at))).all()
    runs = (await db.execute(
        select(AnalysisUsage.organization_id, AnalysisUsage.created_at)
    )).all()
    return retention.build_cohorts(
        [{"id": o.id, "created_at": o.created_at} for o in orgs],
        [{"organization_id": r.organization_id, "created_at": r.created_at} for r in runs],
    )


@router.get("/funnel")
async def funnel_gate(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """The conversion gate: the visitor -> completed-signup funnel with the single
    biggest drop-off named, derived from real funnel events. Founder-readable only.
    Conversion stops where retention starts, so this covers visitor -> completed
    signup and the retention gate takes it from activation onward."""
    rows = (await db.execute(
        select(FunnelEvent.event, FunnelEvent.anon_id, FunnelEvent.created_at, FunnelEvent.source)
    )).all()
    return funnel.build_funnel(
        [{"event": r.event, "anon_id": r.anon_id, "created_at": r.created_at, "source": r.source}
         for r in rows]
    )


@router.get("/analysis-costs")
async def analysis_costs(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Real per-run analysis cost from the measured cost logs (agent_logs phase=cost),
    grouped by sport + type, each checked against its 65% margin ceiling. This is the
    live answer to 'what does a football deep analysis actually cost', from our own
    token accounting, not Anthropic's aggregate bill."""
    rows = (await db.execute(
        select(AgentLog.detail, Game.sport)
        .join(Game, Game.id == AgentLog.game_id, isouter=True)
        .where(AgentLog.phase == "cost")
        .order_by(AgentLog.created_at.desc()).limit(2000)
    )).all()

    groups: dict = {}
    for detail, sport in rows:
        d = detail or {}
        total = d.get("total_usd")
        if total is None:
            continue
        deep = (d.get("mode") == "deep") or bool(d.get("grade"))
        sp = (sport or "football").lower()
        key = (sp, "deep_grade" if deep else "standard")
        g = groups.setdefault(key, {"sport": sp, "type": key[1], "deep": deep,
                                    "runs": 0, "sum": 0.0, "max": 0.0})
        g["runs"] += 1
        g["sum"] += float(total)
        g["max"] = max(g["max"], float(total))

    out = []
    for g in groups.values():
        avg = round(g["sum"] / g["runs"], 4)
        cr = credits.credits_for(sport=g["sport"], deep=g["deep"], is_rerun=False)
        revenue = round(cr * credits.FLOOR_CREDIT_PRICE, 2)
        out.append({
            "sport": g["sport"], "type": g["type"], "runs": g["runs"],
            "avg_usd": avg, "max_usd": round(g["max"], 4),
            "credits": cr, "revenue_at_floor": revenue,
            "max_cogs": credits.max_cogs_at_floor(cr),
            "margin_at_floor": round(1 - avg / revenue, 4) if revenue else None,
            "verdict": credits.margin_verdict(avg, cr),
        })
    out.sort(key=lambda x: (x["sport"], x["type"]))
    return {"margin_floor": credits.MARGIN_FLOOR, "floor_credit_price": credits.FLOOR_CREDIT_PRICE,
            "total_runs": sum(g["runs"] for g in groups.values()), "groups": out}


@router.get("/detection-quality")
async def detection_quality_gate(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """The detection-quality gate: does the film agent actually chop the plays.

    Recall (plays found vs plays the coach had to add back), label-edit rate, and
    timeliness, per game and cut by film resolution, all from our own data. This is
    the number that says whether film analysis is 'top notch' before a coach ever
    sees it. Recall is a FLOOR unless a true play count is supplied per game."""
    from sqlalchemy import case
    from backend.models.event import Event
    from backend.models.learning import CoachLabelCorrection

    auto_b = Event.extra_data["auto_detected"].as_boolean()
    nr_b = Event.extra_data["needs_review"].as_boolean()
    conf_f = Event.extra_data["confidence"].as_float()

    ev_rows = (await db.execute(
        select(
            Event.game_id,
            func.count().label("total"),
            func.sum(case((auto_b == True, 1), else_=0)).label("auto"),
            func.sum(case((nr_b == True, 1), else_=0)).label("needs_review"),
            func.avg(case((auto_b == True, conf_f), else_=None)).label("avg_conf"),
        ).group_by(Event.game_id)
    )).all()

    corr_rows = (await db.execute(
        select(CoachLabelCorrection.game_id, func.count().label("n"))
        .where(CoachLabelCorrection.was_auto_detected == True)  # noqa: E712
        .group_by(CoachLabelCorrection.game_id)
    )).all()
    corr_by_game = {r.game_id: int(r.n) for r in corr_rows if r.game_id}

    # Latest measured cost log per game -> timeliness + ingested resolution.
    cost_rows = (await db.execute(
        select(AgentLog.game_id, AgentLog.detail)
        .where(AgentLog.phase == "cost")
        .order_by(AgentLog.created_at.desc()).limit(3000)
    )).all()
    cost_by_game: dict = {}
    for gid, detail in cost_rows:
        if gid and gid not in cost_by_game:
            cost_by_game[gid] = detail or {}

    game_ids = {r.game_id for r in ev_rows if r.game_id}
    game_meta: dict = {}
    if game_ids:
        grows = (await db.execute(
            select(Game.id, Game.sport, Game.film_height, Game.title, Game.game_date,
                   Game.true_play_count)
            .where(Game.id.in_(game_ids))
        )).all()
        game_meta = {g.id: g for g in grows}

    games = []
    for r in ev_rows:
        gid = r.game_id
        if not gid:
            continue
        auto = int(r.auto or 0)
        total = int(r.total or 0)
        # Only score games that actually had an AI DETECTION run: at least one
        # auto-detected play, or a measured cost log. This drops live-logged /
        # scout / manual-only records (0 auto, no run) so they stop showing as
        # false "0% recall / STOP" rows.
        if auto == 0 and gid not in cost_by_game:
            continue
        meta = game_meta.get(gid)
        cost = cost_by_game.get(gid, {})
        fh = cost.get("film_height")
        if fh is None and meta is not None:
            fh = meta.film_height
        games.append({
            "game_id": str(gid),
            "sport": (meta.sport if meta else None),
            "title": (meta.title if meta else None),
            "game_date": (meta.game_date.isoformat() if meta and meta.game_date else None),
            "auto_plays": auto,
            "coach_added_plays": max(total - auto, 0),
            "true_plays": (meta.true_play_count if meta and meta.true_play_count else None),
            "corrections": corr_by_game.get(gid, 0),
            "needs_review": int(r.needs_review or 0),
            "avg_confidence": round(float(r.avg_conf), 3) if r.avg_conf is not None else None,
            "elapsed_seconds": cost.get("elapsed_seconds"),
            "film_seconds": cost.get("film_seconds"),
            "film_height": fh,
        })

    # Newest first (games without a date sort last).
    games.sort(key=lambda g: g["game_date"] or "", reverse=True)
    return detection_quality.build_scorecard(games)


class TrueCountUpdate(BaseModel):
    true_count: Optional[int] = None  # None or 0 clears it (back to the proxy floor)


@router.put("/detection-quality/{game_id}/true-count")
async def set_true_play_count(game_id: str, body: TrueCountUpdate,
                              user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Set (or clear) the admin-confirmed true play/event count for a game. With it
    set, the game's row on the Film Quality gate shows real (labeled) recall instead
    of the coach-added floor. Pass null or 0 to clear it."""
    game = (await db.execute(select(Game).where(Game.id == game_id))).scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if body.true_count is not None and body.true_count < 0:
        raise HTTPException(status_code=400, detail="true_count cannot be negative")
    game.true_play_count = (body.true_count or None)
    await db.commit()
    return {"ok": True, "game_id": game_id, "true_play_count": game.true_play_count}


@router.get("/orgs")
async def list_orgs(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Organization).order_by(Organization.created_at.desc()).limit(200))
    orgs = result.scalars().all()
    return [{"id": str(o.id), "name": o.name, "slug": o.slug, "subscription_tier": o.subscription_tier, "is_trial": o.is_trial, "has_coach_tenure_access": o.has_coach_tenure_access, "created_at": o.created_at.isoformat()} for o in orgs]

class OrgUpdate(BaseModel):
    subscription_tier: Optional[str] = None
    is_trial: Optional[bool] = None
    has_coach_tenure_access: Optional[bool] = None
    # NOTE: admin_level is deliberately NOT settable here. Minting a platform admin
    # must not be possible through a general-purpose org PATCH (privilege-escalation
    # blast radius). Change admin_level directly in the DB for the rare real case.

@router.patch("/orgs/{org_id}")
async def update_org(org_id: str, body: OrgUpdate, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if updates:
        await db.execute(update(Organization).where(Organization.id == org_id).values(**updates))
        await db.commit()
    return {"ok": True}

@router.delete("/orgs/{org_id}")
async def delete_org(org_id: str, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Permanently delete an organization and everything under it (users, teams,
    roster, games, reports, ...) via ON DELETE CASCADE. Platform-admin only, and you
    cannot delete your own org (self-lockout guard). Irreversible."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if str(org.id) == str(user.organization_id):
        raise HTTPException(status_code=400, detail="You cannot delete your own organization.")
    n = (await db.execute(select(func.count()).select_from(User).where(User.organization_id == org.id))).scalar() or 0
    name, slug = org.name, org.slug
    await db.delete(org)
    await db.commit()
    return {"ok": True, "deleted": {"id": org_id, "name": name, "slug": slug}, "users_removed": n}

@router.get("/risk-flags")
async def list_risk_flags(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RiskFlag).where(RiskFlag.resolved_at == None).order_by(RiskFlag.created_at.desc()).limit(100))
    flags = result.scalars().all()
    return [{"id": str(f.id), "flag_type": f.flag_type, "severity": f.severity, "details": f.details, "created_at": f.created_at.isoformat()} for f in flags]

@router.post("/submissions/{submission_id}/approve")
async def approve_submission(submission_id: str, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TeamSubmission).where(TeamSubmission.id == submission_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    sub.status = "approved"
    sub.reviewed_by = user.id
    sub.reviewed_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}

@router.post("/submissions/{submission_id}/feature")
async def feature_submission(submission_id: str, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TeamSubmission).where(TeamSubmission.id == submission_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    month_year = sub.month_year
    featured = FeaturedTeam(submission_id=sub.id, month_year=month_year)
    sub.status = "featured"
    sub.reviewed_by = user.id
    sub.reviewed_at = datetime.utcnow()
    db.add(featured)
    await db.commit()
    return {"ok": True}

@router.get("/stats")
async def platform_stats(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from backend.models.game import Game
    from backend.models.report import TendencyReport
    orgs = await db.execute(select(func.count()).select_from(Organization))
    users = await db.execute(select(func.count()).select_from(User))
    games = await db.execute(select(func.count()).select_from(Game))
    reports = await db.execute(select(func.count()).select_from(TendencyReport))
    return {
        "total_orgs": orgs.scalar() or 0,
        "total_users": users.scalar() or 0,
        "total_games": games.scalar() or 0,
        "total_reports": reports.scalar() or 0,
    }
