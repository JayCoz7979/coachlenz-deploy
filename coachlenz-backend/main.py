import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from lib.telegram import send_telegram
from routers import auth, teams, players, games, stats, practice, dashboard

load_dotenv()

FRONTEND_URL = os.getenv("COACHLENZ_FRONTEND_URL", "http://localhost:3000")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await send_telegram(
        "🏈 <b>CoachLenz API</b> started successfully!\n"
        "Platform: Sports Coaching Admin\n"
        "Built by Cosby AI Solutions, LLC"
    )
    yield
    # Shutdown
    await send_telegram("⚠️ <b>CoachLenz API</b> is shutting down.")


app = FastAPI(
    title="CoachLenz API",
    description="Sports coaching admin platform — Cosby AI Solutions, LLC",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(teams.router, prefix="/api/v1")
app.include_router(players.router, prefix="/api/v1")
app.include_router(games.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")
app.include_router(practice.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "CoachLenz API",
        "version": "1.0.0",
        "built_by": "Cosby AI Solutions, LLC",
    }


@app.get("/")
async def root():
    return {
        "message": "CoachLenz API — Sports Coaching Admin Platform",
        "docs": "/docs",
        "health": "/health",
        "built_by": "Cosby AI Solutions, LLC",
        "website": "https://cosbyaisolutions.com",
    }
