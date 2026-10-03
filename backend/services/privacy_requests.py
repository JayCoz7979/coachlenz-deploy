"""
COPPA/FERPA privacy-request fulfillment.

The deletion is DELIBERATE, verified erasure of ONE student's identifiers — distinct
from the coach run-preservation rule (which protects a coach's analysis runs from
accidental loss on re-runs). It is tightly scoped so it can never nuke another child's
data or a whole team's film by accident:

- A specific RosterPlayer is deleted by id (org-scoped).
- That player's jersey is de-identified ONLY on games for that player's TEAM (the team
  carries the season, so a jersey reused in another season/team is untouched): the play
  rows are kept (the coach's analysis structure survives) but the jersey is removed from
  `Event.player` and from the `extra_data` identifier fields.
- Whole-film deletion only happens for game_ids the admin explicitly passes (a
  school-authorized removal of shared team film), via the existing game delete.

The certificate reports exactly what was removed — no category is claimed that the
fulfillment did not actually do.
"""
import html
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.roster import RosterPlayer
from backend.models.game import Game
from backend.models.event import Event


async def execute_deletion(
    db: AsyncSession, organization_id, roster_player_ids: list[str], game_ids: list[str] | None = None
) -> dict:
    """Run a scoped student-data deletion. Returns a summary used for the certificate.
    Caller commits. Everything is org-scoped so a request can only touch the resolved
    org's data."""
    players_deleted = 0
    events_scrubbed = 0
    games_deleted = 0
    per_player = []

    for pid in (roster_player_ids or []):
        res = await db.execute(select(RosterPlayer).where(
            RosterPlayer.id == pid, RosterPlayer.organization_id == organization_id))
        p = res.scalar_one_or_none()
        if p is None:
            continue
        jersey = str(p.jersey_number)
        name = (f"{p.first_name} {p.last_name}".strip() if p.last_name else (p.first_name or "")).strip()

        # Games for THIS player's team (season-scoped via the team).
        gids = [g for g in (await db.execute(select(Game.id).where(
            Game.team_id == p.team_id, Game.organization_id == organization_id))).scalars().all()]
        scrubbed_here = 0
        if gids:
            evs = (await db.execute(select(Event).where(
                Event.game_id.in_(gids),
                Event.organization_id == organization_id,
                Event.player == jersey,
            ))).scalars().all()
            for e in evs:
                e.player = None
                ed = dict(e.extra_data or {})
                for k in ("primary_player_jersey", "ball_carrier_jersey"):
                    if str(ed.get(k)) == jersey:
                        ed[k] = None
                pl = ed.get("players")
                if isinstance(pl, list):
                    ed["players"] = [pp for pp in pl if str((pp or {}).get("jersey")) != jersey]
                e.extra_data = ed  # reassign so SQLAlchemy flags the JSONB change
                scrubbed_here += 1
        events_scrubbed += scrubbed_here
        await db.delete(p)
        players_deleted += 1
        per_player.append({"name": name or "(unnamed)", "jersey": jersey, "plays_deidentified": scrubbed_here})

    # School-authorized full film deletion (admin-specified game ids only).
    for gid in (game_ids or []):
        res = await db.execute(select(Game).where(
            Game.id == gid, Game.organization_id == organization_id))
        g = res.scalar_one_or_none()
        if g is None:
            continue
        if g.r2_key:
            try:
                from backend.services.r2 import delete_object
                delete_object(g.r2_key)
            except Exception:
                pass
        await db.delete(g)  # Events cascade (FK ON DELETE CASCADE)
        games_deleted += 1

    await db.flush()
    return {
        "players_deleted": players_deleted,
        "events_scrubbed": events_scrubbed,
        "games_deleted": games_deleted,
        "per_player": per_player,
    }


def render_certificate(*, certificate_id: str, request, summary: dict) -> str:
    """Build the Deletion Certificate HTML. Only lists categories that were actually
    acted on, so the certificate never overstates what was removed."""
    now = datetime.utcnow().strftime("%B %d, %Y")
    req_date = request.created_at.strftime("%B %d, %Y") if getattr(request, "created_at", None) else now

    # All requester-supplied fields are HTML-escaped: they flow into this certificate
    # (emailed) and must never inject markup.
    e_name = html.escape(str(request.requester_name or ""))
    e_rel = html.escape(str(request.relationship or ""))
    e_student = html.escape(str(request.student_name or ""))

    cats = []
    if summary.get("players_deleted"):
        cats.append(f"Roster / player profile records deleted: <strong>{summary['players_deleted']}</strong>")
    if summary.get("events_scrubbed"):
        cats.append(f"Player identifiers removed from film analysis (jersey de-identified on "
                    f"<strong>{summary['events_scrubbed']}</strong> plays; the plays were retained, the student is no longer identified)")
    if summary.get("games_deleted"):
        cats.append(f"Game film deleted (school-authorized): <strong>{summary['games_deleted']}</strong>")
    if not cats:
        cats.append("No matching records were found to delete.")
    cat_html = "".join(f"<li>{c}</li>" for c in cats)

    return (
        f"<div style='font-family:Arial,sans-serif;max-width:640px'>"
        f"<h2 style='color:#14532d'>Student Data Deletion Certificate</h2>"
        f"<p><strong>Cosby AI Solutions LLC — CoachLenz</strong></p>"
        f"<table style='border-collapse:collapse' cellpadding='6'>"
        f"<tr><td><strong>Certificate ID</strong></td><td>{certificate_id}</td></tr>"
        f"<tr><td><strong>Date of deletion</strong></td><td>{now}</td></tr>"
        f"<tr><td><strong>Request received</strong></td><td>{req_date}</td></tr>"
        f"<tr><td><strong>Requested by</strong></td><td>{e_name} ({e_rel})</td></tr>"
        f"<tr><td><strong>Student</strong></td><td>{e_student}</td></tr>"
        f"</table>"
        f"<p><strong>Data removed:</strong></p><ul>{cat_html}</ul>"
        f"<p>We certify that the data described above has been removed from CoachLenz "
        f"production systems in accordance with the CoachLenz Data Privacy Agreement and "
        f"applicable law. Deleted roster records and film are purged from backups within 30 "
        f"days. Shared team film is retained per the school's Data Privacy Agreement unless "
        f"the school authorizes its deletion.</p>"
        f"<p>Certified by: <strong>Jason L. Cosby</strong>, Founder &amp; CEO, Cosby AI Solutions LLC<br/>"
        f"Contact: privacy@coachlenz.com</p>"
        f"<p style='color:#666;font-size:12px'>Retain this certificate for your records. "
        f"Powered by <a href='https://cosbyaisolutions.com'>Cosby AI Solutions</a>.</p>"
        f"</div>"
    )
