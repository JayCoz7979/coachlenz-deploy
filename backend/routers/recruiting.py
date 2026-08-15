"""
Recruiting Board (Track 5.2). Opt-in, per-player showcase: a coach marks clips as a
roster player's recruiting highlights, opts the player in (which mints a share
token), and can send a no-login profile link to a college scout.

Privacy note: the PUBLIC profile intentionally shows the player's NAME — that is the
whole point of a recruiting profile, and it is strictly opt-in per player by a coach
(treated as the school permitting disclosure of athletic directory information).
Everything else that shares publicly (report share links) still hides player names.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta
import secrets

from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.roster import RosterPlayer
from backend.models.clip import Clip
from backend.models.team import Team
from backend.services.auth import get_current_user, get_current_org, require_permission
from backend.services.permissions import CAN_MANAGE_ROSTER
from backend.utils.timeutils import to_naive_utc
from backend.services.email_service import send_recruiting_profile_email
from backend.services.player_stats import stat_line_for, top_play_types
from backend.services.playback import clip_playback
from backend.services.agent_log import log_agent_action
from backend.services.legal import RECRUITING_DIRECTORY_VERSION, RECRUITING_DIRECTORY_ATTESTATION
from backend.services import feature_flags
from backend.routers.roster import team_season_events

router = APIRouter(prefix="/recruiting", tags=["recruiting"])

APP_URL = "https://app.coachlenz.com"
RECRUIT_DEFAULT_DAYS = 30
RECRUIT_MAX_DAYS = 90

# Managing recruiting (opt-in, marking highlights, sending) needs can_manage_roster
# (head coach / coordinators / owner).
_require_manage = Depends(require_permission(CAN_MANAGE_ROSTER))


def clamp_recruiting_days(days) -> int:
    """Recruiting links live 30 days by default, 90 max."""
    try:
        d = int(days)
    except (TypeError, ValueError):
        d = RECRUIT_DEFAULT_DAYS
    return max(1, min(RECRUIT_MAX_DAYS, d))


class EnableIn(BaseModel):
    expires_in_days: int = RECRUIT_DEFAULT_DAYS
    disclosure_consent: bool = False  # #17: coach affirms authority to publish this athlete's profile


class MarkIn(BaseModel):
    clip_id: str
    player_id: str


class SendIn(BaseModel):
    scout_email: EmailStr


async def _player(player_id: str, org_id, db: AsyncSession) -> RosterPlayer:
    res = await db.execute(select(RosterPlayer).where(
        RosterPlayer.id == player_id, RosterPlayer.organization_id == org_id))
    p = res.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Player not found")
    return p


async def _highlights(player_id, org_id, db: AsyncSession):
    res = await db.execute(select(Clip).where(
        Clip.recruiting_player_id == player_id, Clip.organization_id == org_id
    ).order_by(Clip.created_at))
    return res.scalars().all()


async def _recruiting_stats(p: RosterPlayer, org_id, highlights_count: int, db: AsyncSession):
    """Season stats block for a recruiting profile: highlight count plus real
    per-player numbers derived from the player's team games. A player with no team or
    no tagged plays yet reports zeros (still a valid, if empty, profile)."""
    events = []
    team_id = getattr(p, "team_id", None)
    if team_id:
        events, _ = await team_season_events(str(team_id), org_id, db)
    line = stat_line_for(events, p.jersey_number)
    stats = {
        "highlights_count": highlights_count,
        "plays": line["plays"],
        "primary_plays": line["primary_plays"],
        "total_yards": line["total_yards"],
        "games": line["games"],
    }
    return stats, top_play_types(line)


@router.post("/players/{player_id}/enable")
async def enable_recruiting(player_id: str, body: EnableIn, coach: User = _require_manage,
                            db: AsyncSession = Depends(get_db)):
    """Opt this player into the Recruiting Board and (re)issue a share link."""
    p = await _player(player_id, coach.organization_id, db)
    # #17 disclosure-consent gate (flag-gated). Minting a public link publishes a
    # minor's identity to third parties, a distinct authorization from the
    # student_data COLLECTION attestation. Require the coach to accept the directory
    # disclosure for THIS player before a link is minted. Consent already on record
    # at the current version satisfies it (re-enabling later won't re-prompt).
    if await feature_flags.is_enabled(db, "recruiting_consent"):
        has_consent = (p.recruiting_consent_at is not None
                       and p.recruiting_consent_version == RECRUITING_DIRECTORY_VERSION)
        if not has_consent and not body.disclosure_consent:
            raise HTTPException(status_code=403, detail={
                "code": "recruiting_consent_required",
                "message": "Confirm you're authorized to publish this athlete's recruiting profile before enabling the link.",
                "attestation": RECRUITING_DIRECTORY_ATTESTATION,
                "version": RECRUITING_DIRECTORY_VERSION,
            })
        if not has_consent:
            p.recruiting_consent_at = datetime.utcnow()
            p.recruiting_consent_by = coach.id
            p.recruiting_consent_version = RECRUITING_DIRECTORY_VERSION
    days = clamp_recruiting_days(body.expires_in_days)
    p.recruiting_enabled = True
    if not p.recruiting_token:
        p.recruiting_token = secrets.token_urlsafe(24)
    p.recruiting_expires_at = datetime.utcnow() + timedelta(days=days)
    await db.commit()
    # FERPA/UATP: minting a public directory link exposes a minor's name + film +
    # stats to anyone with the link. Record who made that disclosure decision, for
    # which player, and for how long — an auditable trail of the exposure.
    # NOTE: this is the audit half. A distinct disclosure-CONSENT gate before the
    # link can be minted still needs a frontend flow to collect it (deferred).
    await log_agent_action(
        action="recruiting_directory_enabled", organization_id=str(coach.organization_id),
        level="info",
        reason="Opted a player into the public recruiting directory (name + film visible via share link).",
        detail={"player_id": player_id, "by": str(coach.id), "expires_in_days": days},
    )
    return {"ok": True, "player_id": player_id, "recruiting_token": p.recruiting_token,
            "expires_at": p.recruiting_expires_at.isoformat(), "expires_in_days": days,
            "share_path": f"/recruiting/share/{p.recruiting_token}"}


@router.delete("/players/{player_id}")
async def disable_recruiting(player_id: str, coach: User = _require_manage,
                             db: AsyncSession = Depends(get_db)):
    p = await _player(player_id, coach.organization_id, db)
    p.recruiting_enabled = False
    p.recruiting_token = None
    p.recruiting_expires_at = None
    await db.commit()
    return {"ok": True, "player_id": player_id, "recruiting_enabled": False}


@router.post("/highlights")
async def mark_highlight(body: MarkIn, coach: User = _require_manage,
                         db: AsyncSession = Depends(get_db)):
    """Mark a clip as a roster player's recruiting highlight (queues it for the board)."""
    p = await _player(body.player_id, coach.organization_id, db)
    cres = await db.execute(select(Clip).where(
        Clip.id == body.clip_id, Clip.organization_id == coach.organization_id))
    clip = cres.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    clip.recruiting_player_id = p.id
    await db.commit()
    return {"ok": True, "clip_id": body.clip_id, "player_id": body.player_id}


@router.delete("/highlights/{clip_id}")
async def unmark_highlight(clip_id: str, coach: User = _require_manage,
                           db: AsyncSession = Depends(get_db)):
    cres = await db.execute(select(Clip).where(
        Clip.id == clip_id, Clip.organization_id == coach.organization_id))
    clip = cres.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    clip.recruiting_player_id = None
    await db.commit()
    return {"ok": True}


@router.get("/players/{player_id}")
async def coach_view(player_id: str, user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    """Coach's view of a player's recruiting profile + highlights + share status."""
    p = await _player(player_id, user.organization_id, db)
    clips = await _highlights(p.id, user.organization_id, db)
    stats, tops = await _recruiting_stats(p, user.organization_id, len(clips), db)
    return {
        "player": {"id": str(p.id), "name": f"{p.first_name} {p.last_name or ''}".strip(),
                   "position": p.position, "grade_year": p.grade_year, "jersey_number": p.jersey_number},
        "recruiting_enabled": p.recruiting_enabled,
        "recruiting_expires_at": p.recruiting_expires_at.isoformat() if p.recruiting_expires_at else None,
        "share_path": (f"/recruiting/share/{p.recruiting_token}" if p.recruiting_token else None),
        "highlights": await clip_playback(clips, user.organization_id, db),
        "stats": stats,
        "top_play_types": tops,
    }


@router.post("/players/{player_id}/send")
async def send_to_scout(player_id: str, body: SendIn, coach: User = _require_manage,
                        org: Organization = Depends(get_current_org),
                        db: AsyncSession = Depends(get_db)):
    p = await _player(player_id, coach.organization_id, db)
    if not p.recruiting_enabled or not p.recruiting_token:
        raise HTTPException(status_code=403, detail="Enable recruiting for this player first.")
    url = f"{APP_URL}/recruiting/share/{p.recruiting_token}"
    name = f"{p.first_name} {p.last_name or ''}".strip()
    try:
        await send_recruiting_profile_email(body.scout_email, name, coach.name, org.name, url)
    except Exception as e:
        # This discloses a minor's PII (name + film + stats) to a third party.
        # A swallowed failure returned a FALSE "sent" confirmation and left no
        # record. Log the failed attempt and tell the coach the truth so they can
        # retry, instead of believing the scout received it.
        await log_agent_action(
            action="recruiting_send_failed", organization_id=str(coach.organization_id),
            level="error", reason=str(e)[:300],
            detail={"player_id": player_id, "sent_to": body.scout_email, "by": str(coach.id)},
        )
        raise HTTPException(status_code=502, detail="We couldn't send the profile email. Please try again.")
    # FERPA/UATP: every external disclosure of a student's directory information
    # must be auditable — who disclosed which athlete's profile to whom, and when.
    await log_agent_action(
        action="recruiting_profile_disclosed", organization_id=str(coach.organization_id),
        level="info", reason="Sent recruiting profile to an external scout.",
        detail={"player_id": player_id, "sent_to": body.scout_email, "by": str(coach.id)},
    )
    return {"ok": True, "sent_to": body.scout_email}


@router.get("/share/{token}")
async def public_profile(token: str, db: AsyncSession = Depends(get_db)):
    """PUBLIC, no-login recruiting profile. Token- and expiry-gated. Shows the
    player's name/position/grade + highlights — opt-in per player by a coach."""
    res = await db.execute(select(RosterPlayer).where(RosterPlayer.recruiting_token == token))
    p = res.scalar_one_or_none()
    if not p or not p.recruiting_enabled or not p.recruiting_token:
        raise HTTPException(status_code=404, detail="This recruiting link is invalid.")
    if not p.recruiting_expires_at or datetime.utcnow() > to_naive_utc(p.recruiting_expires_at):
        raise HTTPException(status_code=410, detail="This recruiting link has expired.")
    clips = await _highlights(p.id, p.organization_id, db)
    stats, tops = await _recruiting_stats(p, p.organization_id, len(clips), db)
    # Sport so the public page can drop football-only stats (e.g. Yards) for basketball.
    sport = None
    if p.team_id:
        sport = (await db.execute(select(Team.sport).where(Team.id == p.team_id))).scalar_one_or_none()
    return {
        "name": f"{p.first_name} {p.last_name or ''}".strip(),
        "position": p.position, "grade_year": p.grade_year,
        "sport": sport,
        "highlights": await clip_playback(clips, p.organization_id, db),
        "stats": stats,
        "top_play_types": tops,
        "shared": True,
    }
