# Stripe pricing setup (one step from done)

Pricing model (LOCKED): **Coach $9.99/mo**, **Athletic Dept $29.99/mo**, plus
purchased-only analysis credits. Annual is the yearly equivalent at **2 months free**
(Coach **$99/yr**, Athletic Dept **$299/yr**). The code is wired; this is the only
manual step left.

## 1. Create the Products + Prices in Stripe (LIVE mode)

In the Stripe Dashboard → Products, create (or reuse) a product per tier and add the
recurring prices. You need the **price IDs** (`price_...`), not the product IDs.

| Tier          | Monthly price | Env var                         | Annual price | Env var                                |
|---------------|---------------|---------------------------------|--------------|----------------------------------------|
| Coach         | $9.99 / month | `STRIPE_PRICE_COACH`            | $99 / year   | `STRIPE_PRICE_COACH_ANNUAL`            |
| Athletic Dept | $29.99 / month| `STRIPE_PRICE_ATHLETIC_DEPT`    | $299 / year  | `STRIPE_PRICE_ATHLETIC_DEPT_ANNUAL`    |
| District      | (sales-set)   | `STRIPE_PRICE_DISTRICT`         | (optional)   | `STRIPE_PRICE_DISTRICT_ANNUAL`         |

Each price must be **recurring** with the right interval (month vs year). The amount
charged is whatever the Stripe price says — the app never hardcodes the dollar figure.

## 2. Set the env vars on the backend (Railway → coachlenz-backend)

Set the monthly vars to go live with monthly billing. Set the annual vars **only when
you want annual live** — until they are set, the annual toggle never appears and annual
checkout is refused with a clear message (nothing half-shows).

```
STRIPE_PRICE_COACH=price_...
STRIPE_PRICE_ATHLETIC_DEPT=price_...
STRIPE_PRICE_COACH_ANNUAL=price_...
STRIPE_PRICE_ATHLETIC_DEPT_ANNUAL=price_...
```

No redeploy of code is needed for the values to take effect beyond the normal env-var
restart. `GET /billing/status` returns `annual_available: true` once the two self-serve
annual IDs are set, which is what reveals the monthly/annual toggle in-app.

## 3. Annual subscribers — monthly included credits (already handled)

Monthly subs get their included allotment reset by each monthly invoice. An annual sub's
invoice fires only once a year, so a monthly cron keeps their included credits refreshing
each month:

- Endpoint: `POST /billing/allotment/run-monthly?key=<RECAP_CRON_SECRET>`
- Runs once a month, resets `included` for ACTIVE ANNUAL subs only (purchased credits
  untouched), idempotent per calendar month.
- Dormant until `RECAP_CRON_SECRET` is set (the same secret the monthly recap uses). Add
  one monthly cron line that hits this URL, or have your existing monthly cron call it
  alongside `/admin/monthly-recap/run-due`.

## Checklist

- [ ] Monthly price IDs created + env set (monthly billing live)
- [ ] Annual price IDs created + env set (annual toggle appears)
- [ ] `RECAP_CRON_SECRET` set + a monthly cron calls `/billing/allotment/run-monthly` (only needed once annual subs exist)

Powered by Cosby AI Solutions.
