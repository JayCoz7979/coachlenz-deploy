# Project: CoachLenz

**Updated:** 2026-06-19

## Core Value

AI film analyst OS for sports coaches — upload game film, get AI-tagged play logs, tendency reports, and printable opponent scouting in minutes instead of hours.

## Platform Identity

- **Product:** CoachLenz v3.7
- **Company:** Cosby AI Solutions, LLC
- **Supabase project:** mbkstodswexxvdgyunio (schema: `coachlenz`)
- **AI model:** claude-sonnet-4-5
- **Deploy target:** Railway (backend Dockerfile + frontend NIXPACKS)
- **Storage:** Cloudflare R2
- **Beta deadline:** June 23, 2026

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS, Zustand |
| Backend | FastAPI (Python 3.11), SQLAlchemy async, Alembic |
| Database | Supabase PostgreSQL (schema: `coachlenz`) |
| AI | Anthropic claude-sonnet-4-5 |
| Storage | Cloudflare R2 |
| Workers | Celery + Redis (8 async queues) |
| Billing | Stripe (4 tiers: Starter/Program/Athletic/District) |
| Email | Resend |
| SMS | Twilio |
| Video capture | yt-dlp, Playwright (Hudl) |
| Monitoring | Sentry |

## Modules Built

1. **Roster** — player management, status tracking, injury notes
2. **Schedule** — game calendar, score entry, results
3. **Statistics** — season stats with AI analysis
4. **Practice Plans** — drill planning with AI generation
5. **Dashboard** — season record, top performers, team health
6. **Film Room** — video ingestion, AI play detection, frame-accurate tagging
7. **Reports** — AI-generated tendency reports, printable PDF, editable plays
8. **Scouting** — two-sided O/D/ST tendency engine, opponent scouting reports
9. **Staff Comms** — coach threads, notifications, drip campaigns
10. **Billing** — Stripe subscriptions, trials, referrals
11. **Admin** — coach management, organization admin

## Sports Supported

Football (full + flag), Basketball, Baseball, Softball, Soccer, Volleyball

## Key Constraints

- UATP compliance required before beta (identity disclosure, action logging, confidence flagging, human escalation)
- `ANTHROPIC_MODEL=claude-sonnet-4-5` — locked, do not change
- Never reference dead Supabase project vjtqtgvxhsbhlpifrzph
- CGE brand colors: Forest Green primary, White/Charcoal/Gold accents — no navy/blue

## Key Decisions

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-06 | Frame density: 5s interval + 0.27 scene threshold, cap 900 | Maximizes detection recall without token blowout |
| 2026-06 | Consecutive-frame batches for AI | Reads play development, not just single-frame snapshots |
| 2026-06 | 8s deduplication window | Eliminates repeat detections of same play from similar frames |
| 2026-06 | Two-sided O/D/ST toggle | Coaches need opponent scouting + self-scouting from same film |
| 2026-06 | Real frame timestamps (not position-based) | Prevents timestamp drift from variable-length video |
