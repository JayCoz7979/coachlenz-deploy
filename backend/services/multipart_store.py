"""Multipart film storage.

Production writes to Cloudflare R2 with the S3 multipart API. Dev and tests, where
R2 credentials are absent, use the same create / part / list / complete / abort
contract on local disk. Callers never send a whole game film through one request.
"""
import hashlib
import json
import os
import shutil
from typing import Optional

from botocore.exceptions import ClientError

from backend.services import r2


class MultipartError(Exception):
    """The upload id is unknown, or it does not belong to the given object key."""


def _local() -> bool:
    return r2._use_local()


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


def complete_upload(key: str, upload_id: str, parts: list[dict]) -> int:
    """Assemble the parts into the final object. Idempotent: a second call after
    a successful assemble returns the object size. Returns that size in bytes."""
    if _local():
        _require_key(upload_id, key)
        existing = object_size(key)
        if existing is not None and not _has_local_parts(upload_id):
            return existing
        ordered = sorted(parts, key=lambda p: p["part_number"])
        dest = r2._safe_local_path(key)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".partial"
        with open(tmp, "wb") as out:
            for part in ordered:
                src = _part_path(upload_id, part["part_number"])
                with open(src, "rb") as inp:
                    shutil.copyfileobj(inp, out, length=1024 * 1024)
        os.replace(tmp, dest)
        shutil.rmtree(_part_dir(upload_id), ignore_errors=True)
        return os.path.getsize(dest)
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
