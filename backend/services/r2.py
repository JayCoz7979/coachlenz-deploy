import boto3
from datetime import datetime, timedelta
from botocore.config import Config
from backend.config import settings

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
    client = get_r2_client()
    url = client.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.R2_BUCKET_NAME, "Key": key, "ContentType": content_type},
        ExpiresIn=3600,
    )
    return {"upload_url": url, "key": key}

def generate_presigned_download_url(key: str, expires_in: int = 604800) -> str:
    client = get_r2_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET_NAME, "Key": key},
        ExpiresIn=expires_in,
    )

def delete_object(key: str):
    client = get_r2_client()
    client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)

def get_download_expiry() -> datetime:
    return datetime.utcnow() + timedelta(days=7)
