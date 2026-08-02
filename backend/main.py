import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from .ratelimit import limiter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import settings
from .routers import (
    auth, teams, games, clips, events, reports, upload, jobs,
    billing, referrals, teams_of_month, coaches, admin, threads,
    playlists, assignments, packages, notifications, me, files, ingest, ai_detect,
    connections, scout, scout_football, onboarding, roster, staff, ad, recruiting, grades,
    legal, report_chat, learning, live_game,
)
from .workers.worker_ai_detect import AiDetectWorker
from .workers.worker_analysis import AnalysisWorker
from .workers.worker_drip import DripWorker
from .workers.worker_ingest import IngestWorker
from .workers.worker_packages import PackagesWorker
from .workers.worker_referrals import ReferralsWorker
from .workers.worker_reports import ReportsWorker

from .observability import init_sentry
init_sentry("api")

app = FastAPI(
    title="CoachLenz API",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Every origin the browser app can be served from must be allowed, or the API
# rejects it via CORS preflight. The app now lives at app.coachlenz.com (custom
# domain); the Railway URL and the marketing site stay valid too. Deduped,
# falsy-filtered so a missing settings.APP_URL never injects a bad origin.
_ALLOWED_ORIGINS = [o for o in dict.fromkeys([
    settings.APP_URL,
    "https://app.coachlenz.com",
    "https://coachlenz.com",
    "https://www.coachlenz.com",
    "https://coachlenz-frontend-production.up.railway.app",
    "http://localhost:3000",
]) if o]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


app.add_middleware(SecurityHeadersMiddleware)


# The heavy hitters: memory/CPU-intensive jobs (film ingest, multi-pass vision
# detection). A crash or OOM in one of these, when run inside the API process,
# takes HTTP serving down with it. WORKERS_IN_API="light" moves them off the API
# onto the dedicated worker service. See config.WORKERS_IN_API.
_HEAVY_WORKERS = {AiDetectWorker, IngestWorker}


@app.on_event("startup")
async def start_workers():
    mode = (settings.WORKERS_IN_API or "all").strip().lower()
    if mode == "none":
        return
    for WorkerClass in [AiDetectWorker, AnalysisWorker, DripWorker, IngestWorker, PackagesWorker, ReferralsWorker, ReportsWorker]:
        if mode == "light" and WorkerClass in _HEAVY_WORKERS:
            continue
        asyncio.create_task(WorkerClass().run_forever())

app.include_router(auth.router)
app.include_router(teams.router)
app.include_router(games.router)
app.include_router(clips.router)
app.include_router(events.router)
app.include_router(reports.router)
app.include_router(upload.router)
app.include_router(jobs.router)
app.include_router(billing.router)
app.include_router(referrals.router)
app.include_router(teams_of_month.router)
app.include_router(coaches.router)
app.include_router(admin.router)
app.include_router(threads.router)
app.include_router(playlists.router)
app.include_router(assignments.router)
app.include_router(packages.router)
app.include_router(notifications.router)
app.include_router(me.router)
app.include_router(files.router)
app.include_router(ingest.router)
app.include_router(ai_detect.router)
app.include_router(connections.router)
app.include_router(scout.router)
app.include_router(scout_football.router)
app.include_router(onboarding.router)
app.include_router(roster.router)
app.include_router(staff.router)
app.include_router(ad.router)
app.include_router(recruiting.router)
app.include_router(grades.router)
app.include_router(legal.router)
app.include_router(report_chat.router)
app.include_router(learning.router)
app.include_router(live_game.router)


@app.get("/health")
async def health():
    # Liveness: the process is up and serving. Cheap, no dependencies.
    return {"status": "ok", "version": "1.0.0", "platform": "CoachLenz"}


@app.get("/health/ready")
async def health_ready(response: Response):
    # Readiness: can we actually serve? Ping the DB. 503 if not, so Railway does
    # not promote a deploy whose Postgres is unreachable (it would serve 500s).
    from .health import db_ready
    ok, err = await db_ready()
    if ok:
        return {"status": "ready", "db": "ok"}
    response.status_code = 503
    return {"status": "not_ready", "db": "error", "detail": err}
