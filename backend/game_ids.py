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
    """A SQLAlchemy DBAPIError for asyncpg's "invalid UUID" DataError.

    SQLAlchemy's asyncpg adapter wraps the driver error, so exc.orig is
    AsyncAdapt_asyncpg_dbapi.Error, its message starts with
    "<class 'asyncpg.exceptions.DataError'>", and the DataError itself is its
    __cause__. Check the whole chain, not just the class name of exc.orig."""
    seen = 0
    err = getattr(exc, "orig", None)
    while err is not None and seen < 5:
        text = str(err)
        if "invalid UUID" in text and (type(err).__name__ == "DataError" or "DataError" in text):
            return True
        err = err.__cause__ or err.__context__
        seen += 1
    return False
