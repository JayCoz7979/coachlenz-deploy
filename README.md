# CoachLenz

Sports coaching admin platform built by Cosby AI Solutions, LLC.

Recent changes are tracked in [CHANGELOG.md](CHANGELOG.md).

## Stack
- **Frontend:** Next.js 14, TypeScript, Tailwind CSS
- **Backend:** FastAPI (Python 3.11)
- **Database:** Supabase (schema: `coachlenz`)
- **AI:** Claude claude-sonnet-4-5

## Modules
1. **Roster** — Player management, status tracking, injury notes
2. **Schedule** — Game calendar, score entry, results
3. **Statistics** — Season stats with AI-powered analysis
4. **Practice Plans** — Drill planning with AI generation
5. **Dashboard** — Season record, top performers, team health

## Retention gate

Before building feature breadth, CoachLenz must clear a retention gate: a live signup
cohort has to come back for the core value moment (a second film analysis within 30
days). The gate is instrumented and founder-readable at Admin, Retention, and derived
from real signup and delivered-analysis events (no new table, no setup or env changes).
The pass bar, stop line, and discipline rule are in [BUILD_STATUS.md](BUILD_STATUS.md);
the value path is documented in [ARCHITECTURE.md](ARCHITECTURE.md).

## Conversion gate

The signup funnel is instrumented end to end (first-party, no third-party trackers) and
founder-readable at Admin, Funnel: visitor, clicked start, reached signup, created
account, completed signup, with the biggest drop-off named. Before scaling any paid
traffic the funnel must clear the conversion gate (visitor to completed signup) in
[BUILD_STATUS.md](BUILD_STATUS.md). No setup or env changes are needed; the landing page
emits anonymous beacon events and signup steps are recorded server-side.

## Traffic and channels

Every visitor is attributed to a source (utm_source, referrer, or direct), carried
through signup so Admin, Funnel, By channel shows visitor-to-signup per channel. A free
tool at `/tools/film-time-saved` targets the core pain and captures leads. The SEO
foundation (metadata, sitemap, robots, structured data) is driven by
`NEXT_PUBLIC_SITE_URL` (set it to the public site origin; it defaults to the app URL).
Prove one channel against the channel gate in [BUILD_STATUS.md](BUILD_STATUS.md) before
scaling it.

## Sports Supported
Football, Basketball, Baseball, Softball, Soccer, Volleyball

## Quick Start

### Backend
```bash
cd coachlenz-backend
cp .env.example .env
# Fill in env vars
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend
```bash
cd coachlenz-frontend
cp .env.local.example .env.local
# Fill in NEXT_PUBLIC_API_URL
npm install
npm run dev
```

## Database
Apply migration via Supabase MCP or run `migrations/001_coachlenz_schema.sql` directly.

---

Powered by [Cosby AI Solutions](https://cosbyaisolutions.com)
