"""
Clip playback URLs — resolved fresh on every read, never stored.

A Clip is a time window into its parent GAME's film; clips carry no file of their
own (r2_key is always null on API-created clips). So a highlight's playable URL is
the game film presigned NOW, plus the clip's start/end for seeking.

Presigning on read (instead of returning a stored r2_url) is the whole point: a
recruiting/share link can outlive the ~7-day presigned URL, and it still plays
because the URL is minted when the page is opened, not when the clip was made.
"""
from typing import Any, Iterable, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.game import Game
from backend.services.r2 import safe_download_url


async def game_key_map(game_ids: Iterable[Any], org_id, db: AsyncSession) -> dict:
    """{game_id -> r2_key} for the given games in this org (missing/other-org ids
    simply don't appear)."""
    ids = {str(g) for g in game_ids if g}
    if not ids:
        return {}
    res = await db.execute(select(Game.id, Game.r2_key).where(
        Game.id.in_(ids), Game.organization_id == org_id))
    return {str(gid): key for gid, key in res.all()}


def _with_fragment(url, start, end):
    """Append an HTML media fragment (#t=start,end) so a plain video link opens at the
    clip window instead of the top of the full game film. The fragment is client-side
    only, so it never disturbs the presigned query signature."""
    if not url or start is None:
        return url
    frag = f"#t={start}" + (f",{end}" if end is not None else "")
    return f"{url}{frag}"


async def clip_playback(clips: Iterable[Any], org_id, db: AsyncSession) -> List[dict]:
    """Serialize clips with a freshly presigned playback URL (of the parent game
    film), seeked to the clip window via a media fragment. `url` is None when the game
    film isn't available yet (still processing) or R2 can't be reached — never an error."""
    clips = list(clips)
    keys = await game_key_map({getattr(c, "game_id", None) for c in clips}, org_id, db)
    out = []
    for c in clips:
        base = safe_download_url(keys.get(str(getattr(c, "game_id", None))))
        out.append({
            "id": str(c.id),
            "game_id": (str(c.game_id) if getattr(c, "game_id", None) else None),
            "title": c.title,
            "start_time": c.start_time,
            "end_time": c.end_time,
            "url": _with_fragment(base, c.start_time, c.end_time),
        })
    return out
