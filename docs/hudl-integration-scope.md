# Hudl "Connect" integration — scope

**Goal:** a coach connects Hudl once and their private team film imports in HD, with
zero cookie-export or technical steps. Hudl is the primary path most coaches use, so
this is the highest-leverage ingest work.

## Reality check (researched 2026-07)
- Hudl's **public APIs are data/stats only** — Hudl IQ / StatsBomb feeds and raw X&Y
  tracking data — and are **partnership-gated** (register via Hudl support, OAuth2
  token issued per approved app).
- **No evidence of a self-serve public API to download/import raw game FILM.** Video
  is delivered through the authenticated web player (token-gated HLS/DASH, no DRM),
  which is why we drive a headless browser to capture the manifest.
- Third-party "Hudl API" integrators exist (e.g. SportsFirst) but appear to be
  partnership/enterprise arrangements, not a self-serve film-download endpoint.

**Implication:** the "official API" path is a **business-development effort** (Hudl
partnership) with an uncertain outcome on film access, not a quick engineering win.
The reliable near-term coach-facing solution is a **hardened server-side capture.**

## Options

| Option | Coach UX | Effort | Risk / dependency |
|---|---|---|---|
| **A. Official Hudl partnership/API** | Best (OAuth "Connect Hudl") | Low eng / high BD | Depends on Hudl approving + exposing film download. Slow, external, uncertain. |
| **B. Hardened server-side login capture** | Good (enter Hudl login once) | Medium eng, ongoing | Hudl login flow changes / bot-detection / 2FA. We control it. |
| **C. Cookie paste** (current stopgap) | Poor (export cookies) | Done | Fragile, expires, not coach-friendly. Keep only as fallback. |

## Recommendation
1. **Pursue A in parallel as business development** — email Hudl partnerships asking
   for API access to a team's film for an authorized third-party analysis app. Low
   cost to ask; if granted, it becomes the long-term path. Do not block on it.
2. **Build B as the real coach-facing solution.** Make the existing connected-account
   login reliable:
   - **Residential proxy** on the capture session (SHIPPED — `YTDLP_PROXY` now also
     routes the Playwright browser) so Hudl doesn't treat us as a datacenter bot.
   - **2FA handling:** when login needs a code, pause and prompt the coach in-app for
     it (a `connections` "verification pending" state + a `POST /connections/verify`
     step), instead of failing.
   - **Session persistence:** after a successful login, store the captured session
     cookies (encrypted) and reuse them for subsequent imports; only re-login when
     they expire. Cuts login attempts (and bot-detection exposure) dramatically.
   - **Login-flow resilience:** the login selectors live in `_perform_login`
     (hudl_capture.py) — keep them current; add clear per-step failure reasons that
     surface to the coach ("Hudl asked for a verification code").
   - **HD selection:** already handled — `-S res` picks the 1080p variant from the
     captured manifest, and the low-res flag verifies it.
3. **Keep C (cookie paste) as the power-user / fallback path** for coaches whose Hudl
   requires SSO/2FA we can't automate.

## Concrete B work items (est.)
- Session-cookie persistence after login (store on `SourceConnection`, reuse) — ~M
- 2FA prompt flow (state + endpoint + UI) — ~M
- Login selector hardening + explicit failure reasons — ~S
- Verify HD end-to-end on a real Hudl game (needs a Hudl account) — ~S

## Already shipped toward this
- Per-org Hudl cookie auth (PR #43) and residential-proxy routing for the capture
  (this PR). `-S res` HD selection + low-res flag (PR #42). Direct HD upload works
  with no auth at all (proven).

## Bottom line
There is no self-serve Hudl film API to plug into, so a coach connecting Hudl reliably
= **hardened server-side login (B) + residential proxy + session persistence + 2FA
prompt**, with an official partnership (A) pursued in parallel. No coach ever exports
a cookie in the happy path.
