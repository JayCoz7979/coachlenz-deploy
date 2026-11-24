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

Add a short line near the hero: "Coming soon. Join the list and you will be
among the first to experience CoachLenz."

Paste `waitlist-section.html` in front of the footer. It is a section, not a
full document. It posts to the same `POST /leads` endpoint as the app. Name,
email, role, and the email-consent box are required. School and sport are
optional. It also sends `utm_source`, `utm_medium`, `utm_campaign`, and
`lead_magnet` when those are on the page URL.

The form only works when the page is served from `https://coachlenz.com` or
`https://www.coachlenz.com`. Those origins are already allowed by the API.
Opening the snippet as a local file will be blocked by the browser.

To revert, put the previous homepage build back and remove the section. The
app flag `signups_enabled` is separate and is how registration itself turns
back on.
