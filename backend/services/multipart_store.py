"""Multipart film storage.

Production writes to Cloudflare R2 with the S3 multipart API. Dev and tests, where
R2 credentials are absent, use the same create / part / list / complete / abort
contract on local disk. Callers never send a whole game film through one request.
"""
import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import time
from typing import Optional

from botocore.exceptions import ClientError

from backend.services import r2


class MultipartError(Exception):
    """The upload id is unknown, or it does not belong to the given object key."""


class UploadBusy(Exception):
    """Local storage: another request held this upload's lock past the deadline."""


def _lock_timeout() -> float:
    try:
        value = float(getattr(r2.settings, "UPLOAD_LOCK_TIMEOUT_SECONDS", 120.0))
    except (TypeError, ValueError):
        return 120.0
    return value if value > 0 else 120.0


def _acquire(lock_fd: int, timeout: float) -> None:
    """Take an exclusive flock without waiting forever. Retries a non-blocking
    lock with a short, growing sleep and raises UploadBusy at the deadline."""
    deadline = time.monotonic() + timeout
    delay = 0.01
    while True:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise UploadBusy("Upload is busy")
            time.sleep(min(delay, remaining))
            delay = min(delay * 2, 0.5)


def _local() -> bool:
    return r2._use_local()


def uses_local_disk() -> bool:
    """True when uploads are stored on local disk (dev, tests, staging)."""
    return _local()


def _root() -> str:
    return r2.LOCAL_STORAGE_DIR


def _etag(data: bytes) -> str:
    return '"' + hashlib.md5(data).hexdigest() + '"'


def _part_dir(upload_id: str) -> str:
    if not upload_id or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for c in upload_id):
        raise MultipartError("Invalid upload id")
    base = os.path.realpath(_root())
    path = os.path.realpath(os.path.join(base, ".multipart", upload_id))
    if path != base and not path.startswith(base + os.sep):
        raise MultipartError("Invalid upload id")
    return path


def _meta_path(upload_id: str) -> str:
    return os.path.join(_part_dir(upload_id), "meta.json")


def _part_path(upload_id: str, part_number: int) -> str:
    return os.path.join(_part_dir(upload_id), f"{int(part_number):05d}")


def _read_meta(upload_id: str) -> dict:
    path = _meta_path(upload_id)
    if not os.path.exists(path):
        raise MultipartError("Upload session not found")
    with open(path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    if not isinstance(meta, dict) or not meta.get("key"):
        raise MultipartError("Upload session not found")
    return meta


def _require_key(upload_id: str, key: str) -> None:
    meta = _read_meta(upload_id)
    if meta.get("key") != key:
        raise MultipartError("Upload session does not match this file")


def create_upload(key: str, content_type: str) -> str:
    """Start a multipart upload. Returns the storage upload id."""
    if _local():
        import secrets
        upload_id = secrets.token_urlsafe(24)
        os.makedirs(_part_dir(upload_id), exist_ok=True)
        with open(_meta_path(upload_id), "w", encoding="utf-8") as f:
            json.dump({"key": key, "content_type": content_type}, f)
        return upload_id
    client = r2.get_r2_client()
    resp = client.create_multipart_upload(
        Bucket=r2.settings.R2_BUCKET_NAME,
        Key=key,
        ContentType=content_type or "video/mp4",
    )
    return resp["UploadId"]


def write_part(key: str, upload_id: str, part_number: int, data: bytes) -> str:
    """Store one chunk. Returns the part ETag."""
    if part_number < 1:
        raise MultipartError("Invalid part number")
    if _local():
        _require_key(upload_id, key)
        path = _part_path(upload_id, part_number)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return _etag(data)
    client = r2.get_r2_client()
    resp = client.upload_part(
        Bucket=r2.settings.R2_BUCKET_NAME,
        Key=key,
        UploadId=upload_id,
        PartNumber=int(part_number),
        Body=data,
    )
    return resp["ETag"]


def list_parts(key: str, upload_id: str) -> list[dict]:
    """Parts already stored, sorted by part number. Each item is
    {part_number, etag, size}."""
    if _local():
        _require_key(upload_id, key)
        directory = _part_dir(upload_id)
        parts = []
        for name in os.listdir(directory):
            if not name.isdigit():
                continue
            path = os.path.join(directory, name)
            if not os.path.isfile(path):
                continue
            with open(path, "rb") as f:
                data = f.read()
            parts.append({
                "part_number": int(name),
                "etag": _etag(data),
                "size": len(data),
            })
        parts.sort(key=lambda p: p["part_number"])
        return parts
    client = r2.get_r2_client()
    parts = []
    marker = None
    while True:
        kwargs = {
            "Bucket": r2.settings.R2_BUCKET_NAME,
            "Key": key,
            "UploadId": upload_id,
        }
        if marker is not None:
            kwargs["PartNumberMarker"] = marker
        try:
            resp = client.list_parts(**kwargs)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchUpload", "NotFound", "404"):
                raise MultipartError("Upload session not found") from exc
            raise
        for p in resp.get("Parts") or []:
            parts.append({
                "part_number": int(p["PartNumber"]),
                "etag": p["ETag"],
                "size": int(p["Size"]),
            })
        if not resp.get("IsTruncated"):
            break
        marker = resp.get("NextPartNumberMarker")
        if marker is None:
            break
    parts.sort(key=lambda p: p["part_number"])
    return parts


def presign_part(key: str, upload_id: str, part_number: int, public_base: str, part_size: int) -> str:
    """A URL the browser can PUT one chunk to. R2 returns a presigned UploadPart
    URL. Local mode returns a signed URL on this API, which is the same pattern
    the single-PUT helper uses when R2 is not configured."""
    if _local():
        import jwt
        from datetime import datetime, timedelta
        sig = jwt.encode(
            {
                "typ": "film-part",
                "upid": upload_id,
                "key": key,
                "pn": int(part_number),
                "max": int(part_size),
                "exp": datetime.utcnow() + timedelta(hours=2),
            },
            r2.settings.SECRET_KEY,
            algorithm="HS256",
        )
        base = public_base.rstrip("/")
        return f"{base}/files/multipart/{upload_id}/{int(part_number)}?sig={sig}"
    client = r2.get_r2_client()
    # Content-Type is intentionally not signed. Browsers attach their own, and a
    # mismatch with a signed Content-Type fails the PUT. UploadPart does not
    # require it; the object type was set when the multipart upload was created.
    return client.generate_presigned_url(
        "upload_part",
        Params={
            "Bucket": r2.settings.R2_BUCKET_NAME,
            "Key": key,
            "UploadId": upload_id,
            "PartNumber": int(part_number),
        },
        ExpiresIn=7200,
    )


def _lock_path(upload_id: str) -> str:
    """A lock file next to the part directory, not inside it.

    complete removes the part directory. The lock has to outlive that so the
    next process can still take it. An in-process lock is not enough: staging
    runs several API processes.
    """
    directory = _part_dir(upload_id)
    parent = os.path.dirname(directory)
    os.makedirs(parent, exist_ok=True)
    return os.path.join(parent, upload_id + ".lock")


def _assembled_size(dest: str, expected: int) -> Optional[int]:
    if expected <= 0 or not os.path.isfile(dest):
        return None
    got = os.path.getsize(dest)
    if got == expected:
        return got
    return None


@contextlib.contextmanager
def upload_lock(upload_id: str, timeout: Optional[float] = None):
    """Hold the per-upload cross-process lock for local storage.

    finish_upload lists the parts, checks them and assembles them inside this
    lock, so a second complete never sees a part directory that the first one
    is still removing. The body must not await: the lock is a blocking flock.
    R2 does not need it (ListParts and CompleteMultipartUpload are atomic
    there), so it is a no-op and R2 behavior is unchanged. An invalid upload id
    takes no lock; the caller's list_parts raises MultipartError as before.

    The wait is bounded: after `timeout` seconds (UPLOAD_LOCK_TIMEOUT_SECONDS by
    default) it raises UploadBusy. Callers run it off the event loop.
    """
    if not _local():
        yield
        return
    try:
        lock_path = _lock_path(upload_id)
    except MultipartError:
        yield
        return
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        _acquire(lock_fd, _lock_timeout() if timeout is None else timeout)
        try:
            yield
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
    finally:
        os.close(lock_fd)


def _assemble_local(key: str, upload_id: str, parts: list[dict]) -> int:
    """Assemble local parts. The caller holds upload_lock(upload_id).

    Two completes used to write the same `<dest>.partial` and the loser left
    zeros in the winner's film. Each attempt now writes a private temp file,
    fsyncs it, and renames it onto the destination only while it holds the lock.
    A caller that arrives after the object is already the expected size returns
    that size and does not rewrite it.
    """
    dest = r2._safe_local_path(key)
    expected = sum(int(p["size"]) for p in parts)
    ready = _assembled_size(dest, expected)
    if ready is not None:
        return ready
    ordered = sorted(parts, key=lambda p: int(p["part_number"]))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix="." + os.path.basename(dest) + ".",
        dir=os.path.dirname(dest),
    )
    try:
        with os.fdopen(fd, "wb") as out:
            for part in ordered:
                src = _part_path(upload_id, int(part["part_number"]))
                with open(src, "rb") as inp:
                    shutil.copyfileobj(inp, out, length=1024 * 1024)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, dest)
        tmp = ""
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass
    shutil.rmtree(_part_dir(upload_id), ignore_errors=True)
    return os.path.getsize(dest)


def _complete_local(key: str, upload_id: str, parts: list[dict], lock_held: bool = False) -> int:
    """Assemble local parts under the exclusive cross-process lock. Pass
    lock_held=True when the caller already holds upload_lock(upload_id); a
    second flock on a new descriptor would wait on itself."""
    if lock_held:
        return _assemble_local(key, upload_id, parts)
    _lock_path(upload_id)  # A bad upload id raises MultipartError, as before.
    with upload_lock(upload_id):
        return _assemble_local(key, upload_id, parts)


def complete_upload(key: str, upload_id: str, parts: list[dict], lock_held: bool = False) -> int:
    """Assemble the parts into the final object. Idempotent: a second call after
    a successful assemble returns the object size. Returns that size in bytes.

    The R2 branch is unchanged. S3 CompleteMultipartUpload (which R2 implements)
    consumes the upload id: the call that wins concatenates the parts once, and
    a concurrent or repeated complete receives NoSuchUpload rather than writing
    the object again. The handler below turns that into the stored size.
    https://docs.aws.amazon.com/AmazonS3/latest/API/API_CompleteMultipartUpload.html

    lock_held applies to local storage only (see upload_lock). R2 ignores it.
    """
    if _local():
        return _complete_local(key, upload_id, parts, lock_held=lock_held)
    client = r2.get_r2_client()
    ordered = sorted(parts, key=lambda p: p["part_number"])
    try:
        client.complete_multipart_upload(
            Bucket=r2.settings.R2_BUCKET_NAME,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={
                "Parts": [
                    {"PartNumber": int(p["part_number"]), "ETag": p["etag"]}
                    for p in ordered
                ]
            },
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code not in ("NoSuchUpload",):
            raise
        size = object_size(key)
        if size is None:
            raise
        return size
    size = object_size(key)
    if size is None:
        raise MultipartError("Stored object missing after complete")
    return size


def _has_local_parts(upload_id: str) -> bool:
    directory = _part_dir(upload_id)
    if not os.path.isdir(directory):
        return False
    return any(name.isdigit() for name in os.listdir(directory))


def abort_upload(key: str, upload_id: str) -> None:
    """Drop stored chunks. Does not delete a fully assembled object."""
    if _local():
        try:
            _require_key(upload_id, key)
        except MultipartError:
            return
        shutil.rmtree(_part_dir(upload_id), ignore_errors=True)
        return
    client = r2.get_r2_client()
    try:
        client.abort_multipart_upload(
            Bucket=r2.settings.R2_BUCKET_NAME,
            Key=key,
            UploadId=upload_id,
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("NoSuchUpload", "NotFound", "404"):
            return
        raise


def object_size(key: str) -> Optional[int]:
    if _local():
        try:
            path = r2._safe_local_path(key)
        except ValueError:
            return None
        if not os.path.isfile(path):
            return None
        return os.path.getsize(path)
    client = r2.get_r2_client()
    try:
        resp = client.head_object(Bucket=r2.settings.R2_BUCKET_NAME, Key=key)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in ("404", "NoSuchKey", "NotFound") or status == 404:
            return None
        raise
    return int(resp["ContentLength"])


def delete_object(key: str) -> None:
    r2.delete_object(key)


def verify_part_signature(sig: str, upload_id: str, part_number: int) -> dict:
    """Validate the query signature on a local part PUT. Returns the claims,
    including `max` (the most bytes this part may contain) and `key`."""
    import jwt
    try:
        data = jwt.decode(sig, r2.settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise MultipartError("Invalid upload signature") from exc
    if data.get("typ") != "film-part":
        raise MultipartError("Invalid upload signature")
    if data.get("upid") != upload_id or int(data.get("pn") or 0) != int(part_number):
        raise MultipartError("Invalid upload signature")
    if not data.get("key"):
        raise MultipartError("Invalid upload signature")
    return data
