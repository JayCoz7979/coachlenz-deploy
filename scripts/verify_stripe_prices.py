#!/usr/bin/env python
"""
Reconcile the LIVE Stripe Price amounts against the rate the billing page charges
for. Confirms decision item 4 from docs/coachlenz-build-spec-v3.1.md: does Stripe
actually charge what customers are shown?

WHY THIS MATTERS — three sources currently disagree on the monthly price:
  * billing page display  (frontend/app/settings/billing/page.tsx): $199 / $399 / $1,999
  * scripts/stripe_setup.py (what it CREATES):                        $49  / $99  / $249
  * v3.0 spec:                                                        $299 / $599 / $2,999
If stripe_setup.py was ever run to create the live prices, customers are being
charged a fraction of the advertised rate. This script reads the ACTUAL prices
from Stripe and tells you which (if any) source is live. Set EXPECTED below to the
rate Team Analysis ratifies, then this becomes a pre-launch guard.

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
# truth for what a customer agreed to pay). Update if Team Analysis ratifies a
# different number; do NOT quietly change it to match a wrong Stripe price.
EXPECTED = {
    "STRIPE_PRICE_COACH":         {"tier": "coach",         "usd": 199,  "interval": "month"},
    "STRIPE_PRICE_ATHLETIC_DEPT": {"tier": "athletic_dept", "usd": 399,  "interval": "month"},
    "STRIPE_PRICE_DISTRICT":      {"tier": "district",      "usd": 1999, "interval": "month"},
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
