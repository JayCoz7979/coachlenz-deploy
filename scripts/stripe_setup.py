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

TIERS = [
    {"name": "CoachLenz Coach", "key": "coach", "price_monthly": 4900},
    {"name": "CoachLenz Athletic Department", "key": "athletic_dept", "price_monthly": 9900},
    {"name": "CoachLenz District", "key": "district", "price_monthly": 24900},
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
