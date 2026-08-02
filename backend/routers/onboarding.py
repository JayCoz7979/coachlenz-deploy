"""
Onboarding — the post-signup flow. A new client verifies identity (email + phone,
for chargeback protection) and then locks in the sport(s) their tier allows. Once
a sport is locked, it is enforced on every film-analysis entry point so the client
cannot flip-flop between sports they did not buy.

This router owns:
    GET  /onboarding/status   what's left to do (verification flags, sport lock, tier max)
    POST /onboarding/sports   lock in the chosen sport(s), bounded by the tier's limit

Email / phone verification endpoints live in the auth router alongside login.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.services.auth import get_current_user, get_current_org
from backend.services.sports import (
    CHOOSABLE_SPORTS, VALID_SPORTS, label, max_sports_for_tier, chosen_sports,
)
from backend.services.twilio_verify import phone_verification_configured
from backend.services import legal as legal_service

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/status")
async def onboarding_status(
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
):
    """Everything the onboarding UI needs to render the next step."""
    max_sports = max_sports_for_tier(org.subscription_tier)
    locked = chosen_sports(org)
    # Phone is a gate ONLY when Twilio Verify is actually configured. If it isn't
    # (or a client can't receive SMS), requiring it would trap the user forever
    # with no way to reach "choose_sport". Email stays the always-on hard gate.
    phone_required = phone_verification_configured()
    return {
        "email_verified": bool(user.email_verified),
        "phone_verified": bool(user.phone_verified),
        "phone_on_file": bool(user.phone),
        "phone_required": phone_required,
        "tier": org.subscription_tier,
        "max_sports": max_sports,
        "chosen_sports": locked,
        "sport_locked": len(locked) > 0,
        "onboarding_completed": bool(org.onboarding_completed),
        "choosable_sports": [{"value": s, "label": label(s)} for s in CHOOSABLE_SPORTS],
        # What still stands between the client and a finished onboarding.
        "next_step": (
            "verify_email" if not user.email_verified else
            "verify_phone" if (phone_required and not user.phone_verified) else
            "choose_sport" if not locked else
            "done"
        ),
    }


class ChooseSportsRequest(BaseModel):
    sports: List[str]
    # COPPA/FERPA: the org's one-time student-data authority attestation, captured
    # here at onboarding so coaches aren't stopped by the just-in-time gate later
    # (on roster / film / scout / live). The checkbox on the sport step sets this.
    student_data_consent: bool = False


@router.post("/sports")
async def choose_sports(
    body: ChooseSportsRequest,
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Lock in the sport(s) for this org, bounded by the tier's limit. Once locked
    it cannot be changed self-serve (a plan change / support action re-opens it),
    which is the whole point: no flip-flopping between sports you didn't buy."""
    # Owner-only: sport lock is a plan-level decision.
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Only the account owner can choose the plan's sport(s).")

    # Identity must be verified first (chargeback protection): email then phone.
    # Phone is enforced only when Twilio Verify is configured; otherwise it would
    # be an unpassable gate. Email is always required.
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Verify your email before choosing your sport.")
    if phone_verification_configured() and not user.phone_verified:
        raise HTTPException(status_code=403, detail="Verify your phone number before choosing your sport.")

    if org.onboarding_completed and chosen_sports(org):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Your plan is already locked to {', '.join(label(s) for s in chosen_sports(org))}. "
                f"Changing sports requires a plan change — contact support."
            ),
        )

    # Normalize + validate.
    picked = []
    for s in body.sports:
        v = (s or "").strip().lower()
        if v not in VALID_SPORTS:
            raise HTTPException(status_code=422, detail=f"'{s}' is not a supported sport.")
        if v not in CHOOSABLE_SPORTS:
            raise HTTPException(status_code=422, detail=f"{label(v)} isn't available to select yet.")
        if v not in picked:
            picked.append(v)

    if not picked:
        raise HTTPException(status_code=422, detail="Pick at least one sport to continue.")

    max_sports = max_sports_for_tier(org.subscription_tier)
    if len(picked) > max_sports:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Your {org.subscription_tier} plan includes {max_sports} "
                f"sport{'s' if max_sports != 1 else ''}. You selected {len(picked)}. "
                f"Upgrade your plan to add more sports."
            ),
        )

    # COPPA/FERPA student-data attestation: capture it here, once, so the coach is
    # not stopped by the just-in-time gate on roster / film / scout / live later.
    # Idempotent — skip if the org already attested at the current version.
    if not await legal_service.has_current_acceptance(db, org.id, "student_data"):
        if not body.student_data_consent:
            raise HTTPException(
                status_code=422,
                detail="Confirm you have consent to provide student-athlete information to continue.",
            )
        ip = request.client.host if request.client else None
        await legal_service.record_acceptance(db, org.id, user.id, "student_data", ip=ip)

    org.chosen_sports = picked
    org.onboarding_completed = True
    flag_modified(org, "chosen_sports")
    await db.commit()
    return {
        "chosen_sports": picked,
        "max_sports": max_sports,
        "onboarding_completed": True,
        "message": f"Locked in: {', '.join(label(s) for s in picked)}.",
    }
