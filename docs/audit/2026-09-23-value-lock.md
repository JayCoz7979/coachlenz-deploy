# GSD: CoachLenz Value Lock

Run date: 2026-09-23. Auditor persona: grumpy 40-year retention strategist.
Scope: whole product. Grounded in the real code (`backend/services/credits.py`,
`entitlements.py`, `trial.py`, the frontend surfaces), not the pricing page or memory.

---

## 1. Verdict headline

**Would a coach be dumb to cancel today? No. Right now they would be dumb to STAY past the first invoice.** The single biggest reason: the $9.99 subscription grants ZERO credits (`WELCOME_CREDITS = 0`, `included` is always 0), so a coach can pay the monthly fee and receive nothing they can see until they ALSO buy a separate credit bundle. The bill and the value are decoupled. That is the textbook churn setup, and it is baked into the pricing model, not the code quality.

Second reason, and this one is a reputation grenade in a tight-knit coaching community: `forfeit()` zeroes a coach's PURCHASED, paid-for, unused credits the moment they cancel. A coach who bought the 250-credit Season bundle for $199, used 100, and cancels loses $79 of credits they already paid for. That is the kind of thing that gets screenshotted and shared in a group text.

Caveat stated plainly: CoachLenz has 0 paying customers. You cannot measure retention on customers you do not have. The value of running this now is to defuse the churn bombs BEFORE customer #1, because in a word-of-mouth market the first ten coaches decide the next hundred.

---

## 2. Value ledger

| Unit | Outcome (coach language) | Visible? | Painkiller / Vitamin | Loss on cancel | Verdict |
|---|---|---|---|---|---|
| Coach tier $9.99/mo | Access to upload + analyze. Grants 0 credits. | No win from the fee alone | Neither until credits bought | Access only | FIX |
| Athletic Dept $29.99/mo | All sports, shared pool (also 0 included), seat caps | Same gap, org-wide | Neither until credits bought | Access + seats | FIX |
| Analysis credits / bundles | The actual film breakdown when spent | Yes, the report | Painkiller | Unused credits are FORFEITED | FIX (forfeit) |
| Film analysis (AI detection) | "It broke down my game film in minutes, not hours" | Yes | Painkiller (the core) | The time-saver | KEEP |
| Tendency / scout report | "I walked in knowing their tendencies" | Yes, the report | Painkiller | Their scouting edge | KEEP |
| Self-scout report | "What am I tipping to opponents" | Yes | Painkiller | Their self-awareness | KEEP |
| Live Game Logger (free) | Real-time charting + halftime report | Yes | Painkiller, but FREE | Nothing paid | KEEP (wedge) |
| Cut-ups | Clip reel by tendency | Yes | Painkiller-ish | Their film room | KEEP |
| Player grades / player tendencies | Per-player reads (deep+grade, Opus-heavy) | Only on deep runs | Vitamin on single-cam | Little | FIX |
| Report AI chat (§13) | Ask the report questions | Only if opened | Vitamin | Nothing | FIX |
| Learning loop (§14) | The AI adapts to the coach's corrections | NO, silent | Painkiller they cannot see | Invisible | FIX |
| One-pager (§11) / maps (§12) | Printable game-plan sheet | Yes, in report | Painkiller | Part of report | KEEP |
| Film packages (paid) | Share clip bundles with staff/players | If used | Vitamin | Low | MERGE |
| Coach Tenure (paid) | Career/tenure tracking | Unclear | Vitamin | Low | KILL or MERGE |
| Multi-game reports (paid) | Combine games into one report | Yes | Painkiller for a real scout | Their season view | KEEP |
| Staff comms / messaging | Team chat, playlists, assignments | If the staff lives there | Vitamin unless daily | Low early | FIX (de-emphasize) |
| Teams of the Month | Public recognition | Yes | Vitamin (marketing) | Nothing | KEEP as marketing, not value |
| Referrals | Earn by referring | Yes | Growth, not value | Nothing | KEEP as growth |

---

## 3. Findings, ranked by retention impact (worst first)

### F1 - The subscription delivers no visible value on its own (CHURN BOMB)
`credits.py`: `WELCOME_CREDITS = 0`, `SUBSCRIPTION_TIERS` grant no credits, and `split_spend` funds spend from `included` first but nothing ever puts credits in `included`. A coach pays $9.99, uploads film, and hits a "buy credits" paywall. The base fee bought a login. On the second invoice they have still seen nothing for the recurring charge unless they separately spent $29+ on a bundle. Distractible customers cancel exactly here.

This directly challenges the Jay-locked 2026-09-05 model ("tiers grant NO credits"). The strategist's call: the access-only split is correct for heavy users who buy big bundles, but it strands the light user who is the one most likely to churn. Fix without abandoning the model: **fund a small monthly `included` allotment that refreshes each cycle** (for example, Coach = enough for ~1 standard analysis/mo; AD = a few), so every billing cycle delivers at least one visible breakdown for the base fee. The plumbing already exists (`included` bucket + `split_spend`), it is just never funded or reset. This is a pricing decision, so it needs your go, not a silent code change. See F1-SPEC.

### F2 - Forfeiting purchased credits on cancel (TRUST + REPUTATION BOMB)
`credits.py::forfeit()` zeroes both `included` and `purchased` on cancellation. Purchased credits were paid for in cash and "never expire while active." Taking them on cancel, in a market where your own stated fear is word-of-mouth spreading faster than you can fix it, is a rage-quit engine. Recommendation: on cancel, forfeit only `included` (the free allotment), and let `purchased` credits either survive into a dormant/free state or be honored for a grace window. At absolute minimum, this must be disclosed loudly at the point of purchase AND at the cancel screen. Pricing/policy decision, needs your go. See F2-SPEC.

### F3 - No forced monthly visible win
The coach's "win" (a scouting report) is event-driven: it only happens when they have an opponent and choose to run film. In a bye week, the off-season, or a slow stretch, the coach opens the app, sees nothing new, and starts questioning the $9.99. There is no delivered, unprompted, per-cycle "here is what CoachLenz did for you." This is the highest-leverage retention feature that does not exist yet. Spec: a monthly (or weekly in-season) recap delivered to the coach - films analyzed, plays broken down, hours saved (plays x a per-play manual estimate), top tendencies surfaced, credits remaining - branded, landing before the renewal charge. See F3-SPEC.

### F4 - The learning loop is invisible
§14 adapts detection to the coach's label corrections, which is real painkiller value, but the coach never sees it happen. Invisible value does not count and does not retain. Fix: surface it - "You corrected 12 labels; CoachLenz applied them, your last breakdown needed 30% fewer edits." Turn a silent background system into a visible monthly win. Folds naturally into F3's recap.

### F5 - No per-account churn signal or save flow
The distribution gates (retention/conversion/channel) are aggregate platform metrics, not per-coach intervention. Nothing detects a single coach who stopped uploading, has an unused credit balance sitting idle, or hit a failed payment, and acts before they decide to leave. And the cancel path (given F2) is a one-click goodbye that also torches their credits. Spec: detect idle-with-credits and failed-payment per org; on cancel, show what they lose and offer a downgrade to a free dormant tier first.

---

## 4. Whole-product retention layer

1. **Monthly visible win:** MISSING. This is the biggest gap. Build F3.
2. **First value speed:** GOOD on the free path (Live Game Logger + the free-trial standard breakdown give a same-day win). WEAK on the paid path: signup -> verify email -> pick sport -> upload -> buy credits -> wait. F1 (included allotment) removes the buy-credits wall for the first win.
3. **Switching cost:** MEDIUM. Film, roster, reports, and learning adjustments accrue in-app, which builds lock-in over a season. Nothing owns the coach's identity the way a phone number or domain would. The learning loop (once visible, F4) is the strongest lock-in you have: "the AI is trained on MY corrections" is hard to leave. Lean into it.
4. **Churn signals:** MISSING per-account. Build F5.
5. **The cancel moment:** HOSTILE. Today it forfeits paid credits (F2) with no save offer (F5). Redesign it into a downgrade-first save.
6. **Price vs value:** The $9.99 access fee is priced FINE for what it unlocks, but it SHOWS no value on its own (F1). The problem is not the number, it is that the fee and the value are decoupled. Fix the visible value, keep the price.

---

## 5. Kill list

- **Coach Tenure (paid feature):** KILL or MERGE. No clear monthly coach outcome; it reads as a resume feature, not a painkiller. Cut it from the paid-feature set or fold any useful piece into the coach profile so it stops padding the "what am I paying for" list.
- **Film packages (paid feature):** MERGE into cut-ups/sharing. As its own paid line it is a vitamin with low loss-on-cancel; as a share button on cut-ups it strengthens a unit coaches already use.
- **Staff comms / messaging:** do not KILL, but stop presenting it as core value. It only retains if the staff genuinely lives there daily, which is unproven. De-emphasize until there is usage.

Killing/merging these three shrinks the "what am I actually paying for" surface and lets the core (analysis -> report -> game plan) stand out.

---

## 6. The "dumb to cancel" build order (highest leverage first)

1. **F1 - Fund a monthly included allotment** so the base fee always delivers at least one visible breakdown per cycle. (Your pricing call. Removes the #1 cancel reason.)
2. **F2 - Stop forfeiting purchased credits on cancel** (or disclose it brutally and offer a dormant tier). Kills the reputation grenade before it can go off with coach #1.
3. **F3 - Ship the monthly recap** (films analyzed, hours saved, tendencies found, credits left). The single highest-leverage retention artifact, and it makes F4 visible for free.
4. **F4 - Surface the learning loop** inside that recap. Turns your strongest lock-in from invisible to felt.
5. **F5 - Per-account churn signal + downgrade-first cancel save.**

Do 1 and 2 before you put this in front of a single paying coach. They are pre-launch trust fixes, not growth features.

---

## SPECS (for the pricing/policy items that need Jay's go)

**F1-SPEC (monthly included allotment):** add `MONTHLY_INCLUDED = {"coach": N, "athletic_dept": M}` to `credits.py`; on subscription activation and on each Stripe renewal (invoice.paid), set `OrgCredits.included = MONTHLY_INCLUDED[tier]` (reset, not accumulate) via a new `credits.grant_monthly_allotment(org, tier)`; `split_spend` already draws `included` first so no spend/refund change is needed. Pick N and M to hold the 65% margin floor at the $0.70 worst-case credit (use `max_cogs_at_floor`).

**F2-SPEC (credit preservation on cancel):** in `credits.forfeit()`, forfeit only the `included` bucket; leave `purchased` intact and move the org to a dormant state where purchased credits are honored if they resubscribe (or for a grace window). If the model must keep forfeiting purchased credits, add an explicit, unmissable disclosure at both the bundle-purchase confirm and the cancel confirm.

**F3-SPEC (monthly recap):** a worker (mirror `worker_reports`) that, per active org per cycle, aggregates from `events` + `agent_logs` (cost phase) + `credits` ledger: films analyzed, plays detected, estimated hours saved (plays x manual-minutes-per-play), top 3 tendencies, credits remaining; render on the existing report/one-pager pipeline, deliver via the existing Resend path, land before the renewal date. Reuses analysis already paid for (no re-detection, no new COGS).

Nothing in sections F1, F2, F3-F5 was auto-coded this run: F1 and F2 change Jay-locked pricing/policy and F3-F5 are new features. Per standing rules (do not change locked pricing, no unapproved outward changes, branch and PR only), these ship on your go. This document is the deliverable; say which of the build order you want built and I will branch it.
