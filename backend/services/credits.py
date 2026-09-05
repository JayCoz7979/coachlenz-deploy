"""
Analysis credits: metering for the expensive deep film analysis (~$50/game COGS).

The free Live Game Logger never touches credits. A billable film analysis spends one
credit, taken from the monthly `included` bucket first, then from rolled-over
`purchased` top-ups. Failed runs are refunded. Numbers live here (config), so the
economics can be tuned without a schema change.

Design notes:
  * split_spend is pure and unit-tested; the DB functions wrap it under a row lock so
    concurrent analyses cannot overspend.
  * OPT-IN BY ROW: has_account() is False until an org is granted credits (on trial
    registration or a paid subscription). ai_detect only gates orgs that have a row,
    so existing orgs keep the legacy monthly-cap behavior and nothing breaks.
"""
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ── Economics (starting values, tune freely). 1 credit = 1 deep film breakdown. ──
CREDITS_PER_ANALYSIS = 1
TRIAL_CREDITS = 1
PLAN_MONTHLY_CREDITS = {
    "coach": 2,
    "athletic_dept": 6,
    "district": 30,
    "enterprise": 300,
}
# Top-up packs: id -> (credits, price_cents). Priced above the ~$50 COGS so a top-up
# never loses money. Sold via one-time Stripe Checkout (inline price_data).
PACKS = {
    "pack_3": (3, 19900),
    "pack_10": (10, 59900),
    "pack_25": (25, 129900),
}


def monthly_credits_for(tier: Optional[str]) -> int:
    return PLAN_MONTHLY_CREDITS.get((tier or "").strip().lower(), 0)


def split_spend(included: int, purchased: int, n: int) -> Optional[Tuple[int, int]]:
    """Pure: how to draw `n` credits, included first then purchased. Returns
    (from_included, from_purchased), or None if the balance cannot cover `n`."""
    if n <= 0:
        return (0, 0)
    if included + purchased < n:
        return None
    from_inc = min(included, n)
    from_pur = n - from_inc
    return (from_inc, from_pur)


async def _row(db: AsyncSession, org_id, *, lock: bool = False):
    from backend.models.credits import OrgCredits
    q = select(OrgCredits).where(OrgCredits.organization_id == org_id)
    if lock:
        q = q.with_for_update()
    return (await db.execute(q)).scalar_one_or_none()


async def has_account(db: AsyncSession, org_id) -> bool:
    """True once the org is on the credit system (has a row)."""
    return (await _row(db, org_id)) is not None


async def balance(db: AsyncSession, org_id) -> dict:
    row = await _row(db, org_id)
    inc = row.included if row else 0
    pur = row.purchased if row else 0
    return {"included": inc, "purchased": pur, "total": inc + pur, "on_system": row is not None}


def _ledger(org_id, kind, amount, inc_delta, pur_delta, ref=None, note=None):
    from backend.models.credits import CreditLedger
    return CreditLedger(organization_id=org_id, kind=kind, amount=amount,
                        included_delta=inc_delta, purchased_delta=pur_delta, ref=ref, note=note)


async def _ensure(db: AsyncSession, org_id):
    from backend.models.credits import OrgCredits
    row = await _row(db, org_id, lock=True)
    if row is None:
        row = OrgCredits(organization_id=org_id, included=0, purchased=0)
        db.add(row)
        await db.flush()
    return row


async def grant_monthly(db: AsyncSession, org_id, tier: str, ref: Optional[str] = None) -> None:
    """Reset the included bucket to the plan's monthly amount (purchased rolls over).
    Idempotent per invoice via `ref`: skip if a grant with this ref already recorded."""
    from backend.models.credits import CreditLedger
    n = monthly_credits_for(tier)
    if ref:
        dup = await db.execute(select(CreditLedger.id).where(
            CreditLedger.kind == "grant", CreditLedger.ref == ref).limit(1))
        if dup.scalar_one_or_none():
            return
    row = await _ensure(db, org_id)
    delta = n - row.included
    row.included = n
    db.add(_ledger(org_id, "grant", delta, delta, 0, ref=ref, note=f"monthly {tier}"))


async def grant_trial(db: AsyncSession, org_id) -> None:
    """One-time starter credits so a new account can run its first analysis."""
    row = await _ensure(db, org_id)
    row.included += TRIAL_CREDITS
    db.add(_ledger(org_id, "trial_grant", TRIAL_CREDITS, TRIAL_CREDITS, 0, note="signup"))


async def add_purchased(db: AsyncSession, org_id, n: int, ref: Optional[str] = None) -> None:
    """Add rolled-over top-up credits. Idempotent per stripe session via `ref`."""
    from backend.models.credits import CreditLedger
    if n <= 0:
        return
    if ref:
        dup = await db.execute(select(CreditLedger.id).where(
            CreditLedger.kind == "purchase", CreditLedger.ref == ref).limit(1))
        if dup.scalar_one_or_none():
            return
    row = await _ensure(db, org_id)
    row.purchased += n
    db.add(_ledger(org_id, "purchase", n, 0, n, ref=ref, note="top-up pack"))


async def spend(db: AsyncSession, org_id, n: int, ref: str) -> bool:
    """Atomically draw `n` credits (included first). Returns False if insufficient.
    Locks the row so concurrent analyses serialize and cannot overspend."""
    row = await _row(db, org_id, lock=True)
    if row is None:
        return False
    plan = split_spend(row.included, row.purchased, n)
    if plan is None:
        return False
    from_inc, from_pur = plan
    row.included -= from_inc
    row.purchased -= from_pur
    db.add(_ledger(org_id, "spend", -n, -from_inc, -from_pur, ref=ref, note="analysis"))
    return True


async def refund_for_job(db: AsyncSession, ref: str) -> None:
    """Reverse the spend tied to a job. Idempotent: a no-op if there was no spend for
    this ref, or a refund was already recorded."""
    from backend.models.credits import CreditLedger
    if not ref:
        return
    spent = (await db.execute(select(CreditLedger).where(
        CreditLedger.kind == "spend", CreditLedger.ref == ref).limit(1))).scalar_one_or_none()
    if not spent:
        return
    already = await db.execute(select(CreditLedger.id).where(
        CreditLedger.kind == "refund", CreditLedger.ref == ref).limit(1))
    if already.scalar_one_or_none():
        return
    row = await _ensure(db, org_id=spent.organization_id)
    inc_back = -spent.included_delta   # spend deltas are negative
    pur_back = -spent.purchased_delta
    row.included += inc_back
    row.purchased += pur_back
    db.add(_ledger(spent.organization_id, "refund", inc_back + pur_back, inc_back, pur_back,
                   ref=ref, note="analysis failed"))
