# Marketing coming-soon page

The public marketing site at https://coachlenz.com is not in this repository.
It is a separate deployment with Cloudflare in front of it. There is no
`static/`, `marketing/`, or Cloudflare Pages config here, and this repo's
Next.js app is the one served at https://app.coachlenz.com.

This folder is a ready-to-use replacement for that marketing homepage while
new signups are closed. It is not wired to any host. Nothing in this change
touches Cloudflare, DNS, or hosting settings.

## Where it would go

Replace the current coachlenz.com homepage with `index.html` (and
`coachlenz-logo.png` beside it) on whatever host serves that site. The page
is one file plus the logo. It does not need a build step.

A simple revert is to put the previous marketing homepage back. Keep that
previous build. This folder does not contain it, because the source was not
in this repo.

`index.html` posts to the same waitlist endpoint as the app:

`POST https://coachlenz-backend-production.up.railway.app/leads`

JSON body: `email` (required), `school` (optional), `sport` (optional),
`source` (`marketing-site`).

The API already allows browser calls from `https://coachlenz.com` and
`https://www.coachlenz.com`. The form will fail from any other origin, and
from a file opened directly on a laptop, because the browser blocks that
cross-origin request. That is expected. Confirm the endpoint with curl
instead (see below). School and sport are stored only after migration 056
has been applied, which the backend deploy does for you.

Existing coaches still sign in at https://app.coachlenz.com/login. This page
links there. It does not create accounts.

The page sends `noindex`. That is a supplement. Swapping this file in is
what actually takes the old marketing pages down.
