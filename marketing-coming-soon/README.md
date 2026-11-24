# Patch for coachlenz.com, not a new site

The marketing site at https://coachlenz.com is not in this repository. It is a
separate Cloudflare-fronted build (hashed files under `/assets/`, Google fonts
Syne, DM Sans, and DM Mono, logo `/assets/coachlenz-logo-LDpDm6HP.png`). Nothing
here changes Cloudflare, DNS, or hosting.

Fetched read-only on 24 Nov 2026. There is no `<video>` and no iframe. The intro
is an animated film-intel panel (the script module
`/assets/football-field-intel-*.js`): a fake matchup, tendency scores, a live
telemetry ticker, and an AI summary. A still of that panel is the Open Graph
image. Keep that intro. Do not replace the homepage with a different page.

## What to change on the live homepage

Leave the nav, the animated hero, the sports, the steps, and the pricing
sections in place. Change only the trial calls to action, and add one section.

Links that currently go to `https://app.coachlenz.com/login` and read like a
signup:

- "Start Free" in the header (there are two)
- "Start free" on the pricing cards (three)
- "Start Free" in the footer
- "Sign up free"
- "Get the free logger"

Point those at `https://app.coachlenz.com/waitlist` (or at `#waitlist` on this
same page once the section below is inserted). The real "Sign in" link stays on
`https://app.coachlenz.com/login`.

Under the hero headline, use this lede: "Game film for school basketball and
football. Join the waitlist and we'll email you when CoachLenz opens, plus a
few free coaching resources before then. Already have an account? You can
still sign in." Keep the real Sign in link on `https://app.coachlenz.com/login`.

Paste `waitlist-section.html` in front of the footer. It is a section, not a
full document. It posts to the same `POST /leads` endpoint as the app. First
name, email, and role are required. There is no consent checkbox. The sentence
above the button is the locked Halftime Sheet line (`cl-halftime-v1`), and Privacy Policy links to
`https://app.coachlenz.com/privacy`. School and sport are optional. Player is
left out of this static snippet because `WAITLIST_PLAYER_ROLE_ENABLED` defaults
off. On the first page load it stores `utm_source`, `utm_medium`,
`utm_campaign`, `utm_content`, `utm_term`, the referrer host, the landing path,
`lead_magnet`, and `ref` in `sessionStorage` (`cl_wl_attr`) and sends them with
the form. Success copy, with email still off, is "You're on the list."

The live button and sentence are locked: "Send me the Halftime Sheet" and
version `cl-halftime-v1`. There is no Player option and no age question.

`ref` is stored as `ref_code` and does not grant a referral reward.

`https://coachlenz.com/privacy` is a 404. Publish `privacy-redirect.html` at
that path so it redirects to `https://app.coachlenz.com/privacy`. This file
does not change Cloudflare or DNS by itself.

The form only works when the page is served from `https://coachlenz.com` or
`https://www.coachlenz.com`. Those origins are already allowed by the API.
Opening the snippet as a local file will be blocked by the browser.

To revert, put the previous homepage build back and remove the section. The
app flag `signups_enabled` is separate and is how registration itself turns
back on.
