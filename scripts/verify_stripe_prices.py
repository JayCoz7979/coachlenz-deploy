#!/usr/bin/env python
"""
Reconcile the LIVE Stripe Price amounts against the rate the billing page charges
for. Confirms decision item 4 from docs/coachlenz-build-spec-v3.1.md: does Stripe
actually charge what customers are shown?

WHY THIS MATTERS: the subscription price a customer pays is a pre-created Stripe Price
object (billing.py references STRIPE_PRICE_COACH / STRIPE_PRICE_ATHLETIC_DEPT by id), so
the real charge lives in Stripe, not in the code. In-repo sources have disagreed on that
number over time (old setup scripts say $199 / $399, the retired marketing site showed
$149 / $299). The current locked, customer-facing rate is Coach $9.99/mo ($99/yr) and
Athletic Dept $29.99/mo ($299/yr), per the app billing page and services/credits.py. This
script reads the ACTUAL Stripe prices and confirms they match that rate before it goes on
any public page.

Run with the secret key + price IDs in the ENVIRONMENT, never in code. On Railway
they already exist:
    railway run python scripts/verify_stripe_prices.py
Or locally:
    STRIPE_SECRET_KEY=sk_live_... \
    STRIPE_PRICE_COACH=price_... \
    STRIPE_PRICE_ATHLETIC_DEPT=price_... \
    STRIPE_PRICE_DISTRICT=price_... \
    python scripts/verify_stripe_prices.py

Exit code 0 = all match EXPECTED, 1 = at least one mismatch/missing. The `stripe`
SDK is already a project dependency.
"""
import os
import sys

import stripe

# EXPECTED = the rate the customer-facing billing page charges for (the source of
# truth for what a customer agreed to pay). Update only to a number Jay has ratified;
# do NOT quietly change it to match a wrong Stripe price.
#
# Locked model: two self-serve tiers. District and enterprise are sales-assisted (no
# self-serve Stripe price in PRICE_MAP), so they are out of scope for this guard.
EXPECTED = {
    "STRIPE_PRICE_COACH":         {"tier": "coach",         "usd": 9.99,  "interval": "month"},
    "STRIPE_PRICE_ATHLETIC_DEPT": {"tier": "athletic_dept", "usd": 29.99, "interval": "month"},
    # Annual prices ($99 / $299, two months free). Annual billing is dormant until these
    # env vars are set (billing.py annual_available()); uncomment to guard them once the
    # annual price IDs are configured in Railway.
    # "STRIPE_PRICE_COACH_ANNUAL":         {"tier": "coach (annual)",         "usd": 99,  "interval": "year"},
    # "STRIPE_PRICE_ATHLETIC_DEPT_ANNUAL": {"tier": "athletic_dept (annual)", "usd": 299, "interval": "year"},
}


def main() -> int:
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        print("STRIPE_SECRET_KEY is not set in the environment. Aborting "
              "(never hardcode it).", file=sys.stderr)
        return 2
    stripe.api_key = key

    print(f"{'tier':14} {'price id':22} {'stripe':>12} {'expected':>10}  result")
    print("-" * 74)
    all_ok = True
    for env_var, exp in EXPECTED.items():
        pid = os.environ.get(env_var)
        if not pid:
            all_ok = False
            print(f"{exp['tier']:14} {'(env unset)':22} {'-':>12} ${exp['usd']:>8}  MISSING price id")
            continue
        try:
            p = stripe.Price.retrieve(pid)
        except Exception as e:  # noqa: BLE001 - surface any lookup failure plainly
            all_ok = False
            print(f"{exp['tier']:14} {pid:22} {'ERROR':>12} ${exp['usd']:>8}  {type(e).__name__}: {e}")
            continue
        amt = (p.unit_amount or 0) / 100
        interval = (p.recurring or {}).get("interval") if p.recurring else None
        ok = (
            abs(amt - exp["usd"]) < 0.005
            and interval == exp["interval"]
            and bool(p.active)
            and (p.currency or "").lower() == "usd"
        )
        all_ok = all_ok and ok
        verdict = "PASS" if ok else (
            f"MISMATCH (interval={interval}, active={p.active}, cur={p.currency})"
        )
        print(f"{exp['tier']:14} {pid:22} ${amt:>10,.2f} ${exp['usd']:>8}  {verdict}")

    print("-" * 74)
    print("ALL PRICES MATCH THE DISPLAYED RATES."
          if all_ok else
          "ONE OR MORE PRICES DO NOT MATCH. Fix in Stripe or update the billing page.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
