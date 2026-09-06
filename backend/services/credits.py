"""
Analysis credits (LOCKED pricing model).

Credits are SEPARATE from the subscription and are 100% purchased in bundles. They
never expire while the account is active and are forfeited on cancellation. The free
Live Game Logger never uses credits.

Subscriptions are cheap access, not credits:
  Coach  $9.99/mo ($99/yr)   one head coach + assistants, own credit wallet.
  AD     $29.99/mo ($299/yr) all sports, unlimited seats, shared school pool with
                             AD-set per-sport / per-coach caps.

A deep film analysis spends a fixed number of credits by type (below), drawn from the
org's wallet, and is refunded if the run fails.

Margin: a 65% gross floor is non-negotiable. Validate against the CHEAPEST credit
price ($0.70 at the Department bundle) versus real compute cost, if it holds at $0.70
it holds everywhere. max_cogs_at_floor() gives the ceiling per analysis size.
"""
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ── Subscription tiers (access only; credits are separate). Prices are reference for
#    the UI; the actual charge is the Stripe price, which must be set to match. ──
SUBSCRIPTION_TIERS = {
    "coach": {"label": "Coach", "monthly_cents": 999, "annual_cents": 9900},
    "athletic_dept": {"label": "Athletic Dept", "monthly_cents": 2999, "annual_cents": 29900},
}

# ── Credits per analysis (LOCKED). deep+grade basketball (60) is PROVISIONAL, pending
#    a validation run, treat as TBD, not final. ──
STANDARD_CREDITS = {"football": 29, "basketball": 27, "flag": 22}
DEEP_GRADE_CREDITS = {"football": 55, "basketball": 60}   # basketball TBD (provisional)
REANALYSIS_CREDITS = 9
_DEFAULT_STANDARD = 29    # safe fallback for an unlisted sport (highest standard)
_DEFAULT_DEEP = 55


def credits_for(sport: Optional[str], deep: bool, is_rerun: bool) -> int:
    """Credit cost of one analysis. Re-analysis is flat; otherwise by sport and whether
    it is the deep+grade path. Unknown sports fall back to the football cost."""
    if is_rerun:
        return REANALYSIS_CREDITS
    s = (sport or "football").strip().lower()
    if deep:
        return DEEP_GRADE_CREDITS.get(s, _DEFAULT_DEEP)
    return STANDARD_CREDITS.get(s, _DEFAULT_STANDARD)


# ── Credit bundles (one-time purchases): id -> (credits, price_cents). ──
BUNDLES = {
    "starter":    (30, 2900),
    "sideline":   (100, 8900),
    "season":     (250, 19900),
    "program":    (500, 36900),
    "department": (1000, 69900),
}

# ── Margin floor: validate the cheapest credit ($0.70, Department) vs real COGS. ──
MARGIN_FLOOR = 0.65
FLOOR_CREDIT_PRICE = 0.70   # Department bundle per-credit price (the worst case)

# Welcome credits granted on signup. 0 by design (credits are purchased); the free
# Live Game Logger is the no-cost way to experience the product. Config knob.
WELCOME_CREDITS = 0


def max_cogs_at_floor(credits: int) -> float:
    """Max compute cost (USD) an analysis of this credit size may cost and still clear
    the 65% gross floor at the cheapest bundle price. Real per-run cost must stay under
    this."""
    revenue = credits * FLOOR_CREDIT_PRICE
    return round(revenue * (1 - MARGIN_FLOOR), 4)


def split_spend(included: int, purchased: int, n: int) -> Optional[Tuple[int, int]]:
    """Pure: draw `n` credits, included bucket first then purchased. Returns
    (from_included, from_purchased) or None if the wallet cannot cover `n`. (Included
    stays 0 under the purchased-only model, but the split keeps spend/refund general.)"""
    if n <= 0:
        return (0, 0)
    if included + purchased < n:
        return None
    from_inc = min(included, n)
    return (from_inc, n - from_inc)


async def _row(db: AsyncSession, org_id, *, lock: bool = False):
    from backend.models.credits import OrgCredits
    q = select(OrgCredits).where(OrgCredits.organization_id == org_id)
    if lock:
        q = q.with_for_update()
    return (await db.execute(q)).scalar_one_or_none()


async def has_account(db: AsyncSession, org_id) -> bool:
    """True once the org has a credit wallet (any bundle purchased or welcome grant)."""
    return (await _row(db, org_id)) is not None


async def balance(db: AsyncSession, org_id) -> dict:
    row = await _row(db, org_id)
    total = (row.included + row.purchased) if row else 0
    return {"balance": total, "on_system": row is not None}


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


async def add_credits(db: AsyncSession, org_id, n: int, ref: Optional[str] = None,
                      note: str = "bundle") -> None:
    """Add purchased credits (never expire while active). Idempotent per stripe session
    via `ref`."""
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
    db.add(_ledger(org_id, "purchase", n, 0, n, ref=ref, note=note))


async def grant_welcome(db: AsyncSession, org_id) -> None:
    """One-time signup grant. No-op when WELCOME_CREDITS is 0 (the default)."""
    if WELCOME_CREDITS <= 0:
        return
    row = await _ensure(db, org_id)
    row.purchased += WELCOME_CREDITS
    db.add(_ledger(org_id, "welcome", WELCOME_CREDITS, 0, WELCOME_CREDITS, note="signup"))


async def spend(db: AsyncSession, org_id, n: int, ref: str) -> bool:
    """Atomically draw `n` credits under a row lock. False if the wallet is short."""
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
    """Reverse the spend tied to a job. Idempotent (no spend, or already refunded)."""
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
    inc_back = -spent.included_delta
    pur_back = -spent.purchased_delta
    row.included += inc_back
    row.purchased += pur_back
    db.add(_ledger(spent.organization_id, "refund", inc_back + pur_back, inc_back, pur_back,
                   ref=ref, note="analysis failed"))


async def forfeit(db: AsyncSession, org_id) -> None:
    """Zero the wallet on cancellation (credits are forfeited when the account lapses)."""
    row = await _row(db, org_id, lock=True)
    if row is None or (row.included == 0 and row.purchased == 0):
        return
    inc, pur = row.included, row.purchased
    row.included = 0
    row.purchased = 0
    db.add(_ledger(org_id, "forfeit", -(inc + pur), -inc, -pur, note="subscription canceled"))
