"""Game ids are UUIDs. One place turns a malformed one into 404.

Before this, a non-UUID game id reached a UUID column and asyncpg raised
DataError, which surfaced as a 500 on every route that takes a game id.

* reject_malformed_game_id: an app-wide dependency (main.py). It checks the
  "game_id" path parameter and the "game_id" query parameter of every route
  and answers 404 "Game not found" before any query, the same answer as a
  missing or another org's game.
* is_invalid_uuid_error: lets main.py map an asyncpg "invalid UUID" DataError
  that still gets through (another id, or an id in a JSON body) to 404 too.
"""
import uuid

from fastapi import HTTPException, Request

GAME_NOT_FOUND = "Game not found"


def is_game_id(value) -> bool:
    """True for the UUID forms asyncpg accepts (32 to 36 characters)."""
    if not isinstance(value, str) or not 32 <= len(value) <= 36:
        return False
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def require_game_id(game_id) -> None:
    if not is_game_id(game_id):
        raise HTTPException(status_code=404, detail=GAME_NOT_FOUND)


async def reject_malformed_game_id(request: Request) -> None:
    for value in (request.path_params.get("game_id"), request.query_params.get("game_id")):
        # An empty query value keeps its old meaning (no filter) on /clips.
        if value not in (None, "") and not is_game_id(value):
            raise HTTPException(status_code=404, detail=GAME_NOT_FOUND)


def is_invalid_uuid_error(exc) -> bool:
    """A SQLAlchemy DBAPIError wrapping asyncpg's DataError for a bad UUID."""
    orig = getattr(exc, "orig", None)
    name = type(orig).__name__ if orig is not None else ""
    return name.endswith("DataError") and "invalid UUID" in str(orig)
