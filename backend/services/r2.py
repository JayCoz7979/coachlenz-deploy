import boto3
import os
from datetime import datetime, timedelta
from botocore.config import Config
from backend.config import settings

LOCAL_STORAGE_DIR = "/tmp/coachlenz-files"
_r2_available = None


def _use_local() -> bool:
    global _r2_available
    if _r2_available is None:
        _r2_available = bool(settings.R2_ACCOUNT_ID and settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY)
    return not _r2_available


def _base_url() -> str:
    return settings.APP_URL.rstrip("/")


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def generate_presigned_upload_url(key: str, content_type: str = "video/mp4") -> dict:
    if _use_local():
        os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)
        upload_url = f"{_base_url()}/files/upload/{key}"
        return {"upload_url": upload_url, "key": key}
    client = get_r2_client()
    url = client.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.R2_BUCKET_NAME, "Key": key, "ContentType": content_type},
        ExpiresIn=3600,
    )
    return {"upload_url": url, "key": key}


def generate_presigned_download_url(key: str, expires_in: int = 604800) -> str:
    if _use_local():
        return f"{_base_url()}/files/{key}"
    client = get_r2_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET_NAME, "Key": key},
        ExpiresIn=expires_in,
    )


def delete_object(key: str):
    if _use_local():
        path = os.path.join(LOCAL_STORAGE_DIR, key.replace("/", os.sep))
        if os.path.exists(path):
            os.remove(path)
        return
    client = get_r2_client()
    client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)


def get_download_expiry() -> datetime:
    return datetime.utcnow() + timedelta(days=7)


def save_local_file(key: str, data: bytes):
    path = os.path.join(LOCAL_STORAGE_DIR, key.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def read_local_file(key: str) -> bytes | None:
    path = os.path.join(LOCAL_STORAGE_DIR, key.replace("/", os.sep))
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()
