import hashlib
from typing import Optional
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from backend.models.abuse import DeviceFingerprint, RiskFlag

DISPOSABLE_DOMAINS = {
    "mailinator.com","guerrillamail.com","temp-mail.org","throwaway.email",
    "maildrop.cc","yopmail.com","sharklasers.com","guerrillamailblock.com",
    "trashmail.com","fakeinbox.com","10minutemail.com","dispostable.com",
    "spamgourmet.com","spamgourmet.org","spamgourmet.net","mailnull.com",
    "spamfree24.org","spam4.me","trashmail.me","discard.email",
}

def get_risk_score(email: str) -> int:
    domain = email.split("@")[-1].lower()
    return 80 if domain in DISPOSABLE_DOMAINS else 0

def fingerprint_request(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    return hashlib.sha256(f"{ip}:{ua}".encode()).hexdigest()

async def check_fingerprint(fp: str, db: AsyncSession) -> bool:
    result = await db.execute(select(DeviceFingerprint).where(DeviceFingerprint.fingerprint == fp))
    record = result.scalar_one_or_none()
    if record and record.is_blocked:
        return False
    if record:
        await db.execute(
            update(DeviceFingerprint)
            .where(DeviceFingerprint.fingerprint == fp)
            .values(request_count=DeviceFingerprint.request_count + 1)
        )
    else:
        db.add(DeviceFingerprint(fingerprint=fp))
    await db.commit()
    return True

async def flag_risk(org_id, user_id, flag_type: str, severity: str, details: dict, db: AsyncSession):
    db.add(RiskFlag(
        organization_id=org_id,
        user_id=user_id,
        flag_type=flag_type,
        severity=severity,
        details=details,
    ))
    await db.commit()
