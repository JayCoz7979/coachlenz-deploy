"""Chunked, direct-to-storage film upload.

Railway's edge closes an HTTP request at 300 seconds. A multi-gigabyte film
posted as one body to the API dies there, every time, on a normal home
connection. The browser instead PUTs fixed-size chunks straight to storage
(R2 multipart, or the local stand-in when R2 is not configured). Each chunk is
small enough to finish well under that cutoff, and a dropped connection resumes
from the chunks already stored.

The game row and the trial slot are created only after the assembled object is
in storage and within the size limit. Starting, interrupting, or aborting an
upload does not insert a game and does not consume a trial game.
"""
import logging
import math
import uuid
from datetime import date, datetime, timedelta

import jwt
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

log = logging.getLogger(__name__)

from backend.config import settings
from backend.models.game import Game
from backend.models.job import Job
from backend.services import multipart_store as store
from backend.services.entitlements import assert_ready_to_analyze
from backend.services.legal import assert_student_consent
from backend.services.multipart_store import MultipartError
from backend.services.r2 import safe_object_name
from backend.services.sports import assert_sport_allowed
from backend.services.trial import can_upload_game, is_trial_active, reserve_trial_game_slot

# Railway's edge kills a request at 300s. 8 MiB is about a minute at 1 Mbps and
# about 11 seconds at the ~6 Mbps seen on the failed production uploads, so a
# single chunk finishes with room to spare. It is also above S3's 5 MiB minimum
# for every part except the last, which R2 enforces.
SINGLE_REQUEST_LIMIT = 8 * 1024 * 1024
DEFAULT_PART_SIZE = 8 * 1024 * 1024
S3_MIN_PART = 5 * 1024 * 1024
MAX_PARTS = 10000
SESSION_HOURS = 48

MSG_TOO_BIG = "This film is over the 20 GB limit."
MSG_PROXY = (
    "This film is too large to upload in one request. "
    "Send it in chunks directly to storage instead."
)
MSG_INCOMPLETE = (
    "The upload stopped before every chunk arrived. "
    "Nothing was added to your library and your trial game was not used. "
    "Select the same file to resume."
)
MSG_STORAGE = (
    "We could not store that film. Nothing was added to your library "
    "and your trial game was not used."
)
MSG_TRIAL = "Trial game limit reached. Upgrade to upload more games."
MSG_TRIAL_AFTER = (
    "Trial game limit reached. This film was not added and your trial game was not used. "
    "Upgrade to upload more games."
)
MSG_EXPIRED = (
    "This upload session expired. Start the upload again. "
    "Your trial game was not used."
)
MSG_BAD_SESSION = (
    "This upload session is not valid. Start the upload again. "
    "Your trial game was not used."
)
USE_CHUNKED_DETAIL = (
    "Upload the film in chunks with the chunked uploader. "
    "A game is created only after the upload finishes, so an interrupted "
    "upload does not use your trial game."
)


def max_upload_bytes() -> int:
    return int(settings.MAX_UPLOAD_BYTES)


def assert_file_size(file_size: int) -> None:
    """Reject an empty file and anything over the configured cap (20 GB)."""
    if file_size is None or int(file_size) <= 0:
        raise HTTPException(status_code=400, detail="Choose a video file to upload.")
    if int(file_size) > max_upload_bytes():
        raise HTTPException(status_code=413, detail=MSG_TOO_BIG)


def enforce_proxy_limit(content_length) -> None:
    """The legacy single-request proxy. Anything that cannot finish well under
    Railway's 300s cutoff is refused here, before a byte is written to storage."""
    if content_length is None or content_length == "":
        return
    try:
        size = int(content_length)
    except (TypeError, ValueError):
        return
    if size > max_upload_bytes():
        raise HTTPException(status_code=413, detail=MSG_TOO_BIG)
    if size > SINGLE_REQUEST_LIMIT:
        raise HTTPException(status_code=413, detail=MSG_PROXY)


def plan_part_layout(file_size: int, part_size: int | None = None) -> tuple[int, int]:
    """Return (part_size, part_count). A file larger than the single-request
    limit always takes more than one part, because the part size is at most
    that limit."""
    size = int(file_size)
    part = int(part_size or DEFAULT_PART_SIZE)
    if part < 1:
        raise HTTPException(status_code=400, detail="Invalid part size")
    # Keep every non-final part legal for R2. Local tests may pass a smaller
    # part size explicitly; the HTTP API never does.
    if part_size is None:
        part = min(part, SINGLE_REQUEST_LIMIT)
        part = max(part, min(S3_MIN_PART, size))
    count = math.ceil(size / part)
    if count > MAX_PARTS:
        part = math.ceil(size / MAX_PARTS)
        count = math.ceil(size / part)
    if count > MAX_PARTS or count < 1:
        raise HTTPException(status_code=413, detail=MSG_TOO_BIG)
    return part, count


def _content_type(raw: str | None) -> str:
    ct = (raw or "").strip() or "video/mp4"
    if len(ct) > 120 or any(c in ct for c in "\r\n"):
        return "video/mp4"
    return ct


def _issue_session(org_id, user_id, key: str, upload_id: str, file_size: int, part_size: int, part_count: int) -> str:
    return jwt.encode(
        {
            "typ": "film-upload",
            "org": str(org_id),
            "uid": str(user_id),
            "key": key,
            "upid": upload_id,
            "size": int(file_size),
            "part": int(part_size),
            "count": int(part_count),
            "exp": datetime.utcnow() + timedelta(hours=SESSION_HOURS),
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )


def read_session(token: str, org) -> dict:
    """Decode an upload session and bind it to the caller's organization."""
    if not token:
        raise HTTPException(status_code=400, detail=MSG_BAD_SESSION)
    try:
        data = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail=MSG_EXPIRED)
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail=MSG_BAD_SESSION)
    if data.get("typ") != "film-upload":
        raise HTTPException(status_code=400, detail=MSG_BAD_SESSION)
    if str(data.get("org")) != str(org.id):
        raise HTTPException(status_code=403, detail="This upload belongs to a different account.")
    key = data.get("key") or ""
    prefix = f"games/{org.id}/"
    if not key.startswith(prefix) or ".." in key:
        raise HTTPException(status_code=400, detail=MSG_BAD_SESSION)
    try:
        data["size"] = int(data["size"])
        data["part"] = int(data["part"])
        data["count"] = int(data["count"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail=MSG_BAD_SESSION)
    if data["size"] <= 0 or data["size"] > max_upload_bytes() or data["count"] < 1:
        raise HTTPException(status_code=400, detail=MSG_BAD_SESSION)
    return data


async def authorize_film_upload(db, user, org, sport: str, file_size: int | None) -> None:
    """The same gates as a film import, run before any byte is stored and again
    before the game row is inserted. A missing student-data consent raises 403
    with the attestation payload the upload page already understands."""
    if not can_upload_game(org):
        raise HTTPException(status_code=403, detail=MSG_TRIAL)
    assert_ready_to_analyze(org, user)
    await assert_student_consent(db, org.id)
    assert_sport_allowed(org, sport)
    if file_size is not None:
        assert_file_size(int(file_size))


def _object_key(org_id, file_name: str) -> str:
    return f"games/{org_id}/{uuid.uuid4()}/{safe_object_name(file_name)}"


async def start_upload(db, user, org, body, *, part_size: int | None = None) -> dict:
    """Begin a multipart upload. Does not insert a game and does not reserve a
    trial slot. `part_size` is for tests; the HTTP API leaves it unset so every
    production part stays inside the single-request budget."""
    await authorize_film_upload(db, user, org, body.sport, body.file_size_bytes)
    assert_file_size(body.file_size_bytes)
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="Give the game a title.")
    if not (body.file_name or "").strip():
        raise HTTPException(status_code=400, detail="Choose a video file to upload.")
    file_size = int(body.file_size_bytes)
    part, count = plan_part_layout(file_size, part_size)
    key = _object_key(org.id, body.file_name)
    try:
        upload_id = store.create_upload(key, _content_type(getattr(body, "content_type", None)))
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("multipart create failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail=MSG_STORAGE)
    token = _issue_session(org.id, user.id, key, upload_id, file_size, part, count)
    return {
        "upload_token": token,
        "key": key,
        "part_size": part,
        "part_count": count,
        "file_size_bytes": file_size,
    }


def sign_parts(org, token: str, part_numbers: list[int], public_base: str) -> dict:
    session = read_session(token, org)
    if not part_numbers:
        raise HTTPException(status_code=400, detail="Choose at least one chunk to upload.")
    if len(part_numbers) > 100:
        raise HTTPException(status_code=400, detail="Sign fewer chunks at a time.")
    urls = []
    seen = set()
    for raw in part_numbers:
        number = int(raw)
        if number in seen:
            continue
        seen.add(number)
        if number < 1 or number > session["count"]:
            raise HTTPException(status_code=400, detail="That chunk is outside this upload.")
        urls.append({
            "part_number": number,
            "url": store.presign_part(
                session["key"], session["upid"], number, public_base, session["part"],
            ),
        })
    return {"parts": urls, "part_size": session["part"], "part_count": session["count"]}


def upload_status(org, token: str) -> dict:
    session = read_session(token, org)
    try:
        parts = store.list_parts(session["key"], session["upid"])
        assembled = False
    except MultipartError:
        # The multipart id is gone once the object is assembled. A retry of
        # complete (the DB commit failed, or the response never came back)
        # should not make the browser send the file again.
        size = store.object_size(session["key"])
        if size != session["size"]:
            raise HTTPException(status_code=400, detail=MSG_BAD_SESSION)
        parts = []
        assembled = True
    return {
        "parts": [{"part_number": p["part_number"], "size": p["size"]} for p in parts],
        "part_size": session["part"],
        "part_count": session["count"],
        "file_size_bytes": session["size"],
        "bytes_received": session["size"] if assembled else sum(p["size"] for p in parts),
        "assembled": assembled,
    }


def accept_relayed_part(org, token: str, part_number: int, data: bytes) -> dict:
    """Same-origin fallback for one chunk when the browser cannot PUT to storage
    (bucket CORS not in place yet). The body is capped at one part, which is
    itself capped at the single-request limit, so this request stays far under
    Railway's 300s cutoff."""
    session = read_session(token, org)
    number = int(part_number)
    if number < 1 or number > session["count"]:
        raise HTTPException(status_code=400, detail="That chunk is outside this upload.")
    if len(data) <= 0:
        raise HTTPException(status_code=400, detail="That chunk was empty.")
    if len(data) > session["part"] or len(data) > SINGLE_REQUEST_LIMIT:
        raise HTTPException(status_code=413, detail=MSG_PROXY)
    try:
        store.write_part(session["key"], session["upid"], number, data)
    except MultipartError:
        raise HTTPException(status_code=400, detail=MSG_BAD_SESSION)
    except Exception:
        raise HTTPException(status_code=502, detail=MSG_STORAGE)
    return {"ok": True, "part_number": number, "size": len(data)}


async def read_capped(request, cap: int) -> bytes:
    """Read a request body, refusing anything past `cap` bytes."""
    buf = bytearray()
    async for chunk in request.stream():
        if len(buf) + len(chunk) > cap:
            raise HTTPException(status_code=413, detail=MSG_PROXY)
        buf.extend(chunk)
    return bytes(buf)


def abort_upload(org, token: str) -> dict:
    """Drop chunks for an upload the coach cancelled. No game row exists yet, so
    there is nothing to refund."""
    session = read_session(token, org)
    try:
        store.abort_upload(session["key"], session["upid"])
    except MultipartError:
        pass
    except Exception:
        raise HTTPException(status_code=502, detail=MSG_STORAGE)
    return {"ok": True}


def _assess(parts: list[dict], part_size: int, part_count: int, file_size: int) -> str:
    """'ok', 'incomplete', or 'too_big'."""
    by_num = {}
    for part in parts:
        number = int(part["part_number"])
        size = int(part["size"])
        if number < 1 or number > part_count or size < 0:
            return "too_big"
        if number in by_num:
            return "too_big"
        by_num[number] = size
    if set(by_num) != set(range(1, part_count + 1)):
        return "incomplete"
    last = file_size - (part_count - 1) * part_size
    if last < 1 or last > part_size:
        return "too_big"
    for number, size in by_num.items():
        expect = part_size if number < part_count else last
        if size > expect:
            return "too_big"
        if size != expect:
            return "incomplete"
    total = sum(by_num.values())
    if total > max_upload_bytes():
        return "too_big"
    if total != file_size:
        return "incomplete"
    return "ok"


async def _existing_game(db, org_id, key: str):
    from sqlalchemy import select
    result = await db.execute(
        select(Game).where(Game.organization_id == org_id, Game.r2_key == key)
    )
    return result.scalar_one_or_none()


def _duration(raw) -> int | None:
    try:
        if raw and float(raw) > 0:
            return int(float(raw))
    except (TypeError, ValueError):
        return None
    return None


def _apply_game_date(game: Game, raw) -> None:
    if not raw:
        return
    try:
        game.game_date = date.fromisoformat(str(raw))
    except ValueError:
        return


async def finish_upload(db, user, org, token: str, body) -> dict:
    """Assemble the object, then insert the game and reserve the trial slot.

    If the chunks are incomplete, nothing is inserted and the trial slot is not
    touched, so the coach can resume. A second call after success returns the
    same game and does not reserve a second slot.
    """
    session = read_session(token, org)
    key = session["key"]
    try:
        parts = store.list_parts(key, session["upid"])
    except MultipartError:
        # Already assembled (resume of a complete that failed before the DB
        # commit). Fall through and let complete_upload return the object.
        parts = []
        already = store.object_size(key)
        if already is None:
            raise HTTPException(status_code=400, detail=MSG_BAD_SESSION)
        if already != session["size"]:
            raise HTTPException(status_code=413, detail=MSG_TOO_BIG)
    else:
        state = _assess(parts, session["part"], session["count"], session["size"])
        if state == "incomplete":
            raise HTTPException(status_code=409, detail=MSG_INCOMPLETE)
        if state == "too_big":
            try:
                store.abort_upload(key, session["upid"])
            except Exception:
                pass
            raise HTTPException(status_code=413, detail=MSG_TOO_BIG)
        try:
            size = store.complete_upload(key, session["upid"], parts)
        except HTTPException:
            raise
        except Exception as exc:
            log.warning("multipart complete failed: %s", type(exc).__name__)
            raise HTTPException(status_code=502, detail=MSG_STORAGE)
        if size != session["size"] or size > max_upload_bytes():
            try:
                store.delete_object(key)
            except Exception:
                pass
            raise HTTPException(status_code=413, detail=MSG_TOO_BIG)

    existing = await _existing_game(db, org.id, key)
    if existing:
        return {"id": str(existing.id), "key": key, "status": existing.status}

    # Re-check the gates now that the file exists. Consent or sport can still
    # refuse the row. The trial slot is reserved in this same transaction, so a
    # failure rolls it back with the game.
    await authorize_film_upload(db, user, org, body.sport, session["size"])
    title = (getattr(body, "title", None) or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="Give the game a title.")
    if not await reserve_trial_game_slot(db, org):
        # The other request may have committed this same upload between our
        # existence check and this reservation. Return that game. A different
        # film that lost the trial race has no row here, so the slot stays put.
        await db.rollback()
        raced = await _existing_game(db, org.id, key)
        if raced:
            return {"id": str(raced.id), "key": key, "status": raced.status}
        raise HTTPException(status_code=403, detail=MSG_TRIAL_AFTER)

    game = Game(
        organization_id=org.id,
        team_id=getattr(body, "team_id", None) or None,
        title=title,
        sport=body.sport,
        opponent=getattr(body, "opponent", None) or None,
        is_home=getattr(body, "is_home", None),
        scout_jersey=getattr(body, "scout_jersey", None) or None,
        opponent_jersey=getattr(body, "opponent_jersey", None) or None,
        scout_attack_dir_h1=getattr(body, "scout_attack_dir_h1", None) or None,
        r2_key=key,
        file_size_bytes=session["size"],
        duration_seconds=_duration(getattr(body, "duration_seconds", None)),
        status="processing",
        is_trial_game=is_trial_active(org),
    )
    _apply_game_date(game, getattr(body, "game_date", None))
    db.add(game)
    await db.flush()
    db.add(Job(
        organization_id=org.id,
        job_type="ingest",
        # No source_url: the ingest worker takes the uploaded-file branch and
        # presigns game.r2_key. A URL import sets source_url and is untouched.
        payload={"game_id": str(game.id)},
    ))
    try:
        await db.commit()
    except IntegrityError:
        # Unique r2_key: the other worker inserted this object first. Its
        # transaction holds the trial slot. Ours rolls back, slot included.
        await db.rollback()
        raced = await _existing_game(db, org.id, key)
        if raced:
            return {"id": str(raced.id), "key": key, "status": raced.status}
        raise
    return {"id": str(game.id), "key": key, "status": "processing"}
