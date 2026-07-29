"""
Stripe setup script — creates products and prices for all CoachLenz tiers.
Run once: python -m scripts.stripe_setup
Outputs env var values to copy into Railway.
"""
import os
import stripe

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
if not stripe.api_key:
    raise ValueError("STRIPE_SECRET_KEY not set")

# Monthly prices in CENTS. MUST match the customer-facing billing page
# (frontend/app/settings/billing/page.tsx) and be verifiable by
# scripts/verify_stripe_prices.py: coach $199, athletic_dept $399, district $1,999.
# (Annual + enterprise prices are intentionally NOT created here — there are no
# STRIPE_PRICE_*_ANNUAL / enterprise env vars or PRICE_MAP entries to wire them to
# yet; that is Track 3.2 annual/PO billing.)
TIERS = [
    {"name": "CoachLenz Coach", "key": "coach", "price_monthly": 19900},
    {"name": "CoachLenz Athletic Department", "key": "athletic_dept", "price_monthly": 39900},
    {"name": "CoachLenz District", "key": "district", "price_monthly": 199900},
]

print("Creating Stripe products and prices...\n")
for tier in TIERS:
    product = stripe.Product.create(name=tier["name"])
    price = stripe.Price.create(
        product=product.id,
        unit_amount=tier["price_monthly"],
        currency="usd",
        recurring={"interval": "month"},
    )
    env_key = f"STRIPE_PRICE_{tier['key'].upper()}"
    print(f"{env_key}={price.id}")

print("\nCopy these env vars to Railway backend service.")
print("Also set STRIPE_WEBHOOK_SECRET after creating a webhook endpoint at /billing/webhook")
