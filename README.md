# CoachLenz

Sports coaching admin platform built by Cosby AI Solutions, LLC.

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
