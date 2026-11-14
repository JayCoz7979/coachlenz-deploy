# SEO release checks (app.coachlenz.com)

A standing gate so a release never silently loses search and AI-answer discoverability.
Run it against a local production build before shipping anything that touches routing,
metadata, `robots.ts`, or `sitemap.ts`.

## Run it

```bash
cd frontend
npm run build                 # also regenerates app/sitemap-data.json from git dates
npm run start -- -p 3100 &    # serve the production build locally
SEO_BASE_URL=http://localhost:3100 npm run seo:check
```

Pages are fetched from the local base; the canonical is validated against the real
production host (`https://app.coachlenz.com`), so a local run proves the production URLs
without touching the live site. Override the host with `SEO_CANONICAL_HOST` if needed.

## What it asserts (fails the run otherwise)

For every route in the sitemap:
- HTTP status is `200`.
- The raw HTML contains the route's expected main content (the per-route table below).
- A non-empty `<title>` is present, and no two routes share the same title.
- A `<link rel="canonical">` is present and is the absolute production URL for that route.

Plus:
- `/robots.txt` returns `200` and contains a `User-Agent` rule and a `Sitemap:` line.
- `/sitemap.xml` returns `200` and is valid (`<urlset>` with at least one `<loc>`).

## Per-route expected main content

| Route                      | Expected string (its H1 / a unique line)      |
|----------------------------|-----------------------------------------------|
| `/`                        | `You lose hours breaking down film`           |
| `/tools/film-time-saved`   | `Film Breakdown`                              |
| `/sample/football`         | `This is a real CoachLenz game breakdown`     |
| `/sample/flag`             | `This is a real CoachLenz game breakdown`     |
| `/sample/basketball`       | `This is a real CoachLenz game breakdown`     |
| `/terms`                   | `Terms of Service`                            |
| `/privacy`                 | `Privacy Policy`                              |

The three `/sample/*` pages render the same framing H1 by design, so they share one
expected string (documented exception); their titles differ per sport.

## sitemap lastmod policy

`app/sitemap-data.json` holds each route's real last-content-change date (the git commit
date of its source file). `scripts/gen-sitemap-dates.mjs` runs at build and refreshes
those dates from git, merging over the committed values; if git is unavailable it keeps
the committed dates. `lastModified` is therefore always a real content date, never one
build timestamp stamped across every URL. When you add a public route, add it to
`sitemap.ts`, `scripts/gen-sitemap-dates.mjs`, `app/sitemap-data.json`, and the table above.

## Scope

Public, indexable routes only. The authenticated app is disallowed in `app/robots.ts` and
is intentionally excluded from the sitemap and from this check.
