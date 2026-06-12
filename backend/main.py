import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import settings
from .routers import (
    auth, teams, games, clips, events, reports, upload, jobs,
    billing, referrals, teams_of_month, coaches, admin, threads,
    playlists, assignments, packages, notifications, me, files,
)

if settings.SENTRY_DSN:
    sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.1, environment=settings.ENVIRONMENT)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="CoachLenz API",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.APP_URL, "http://localhost:3000"],
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


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "platform": "CoachLenz"}
