"""
HTTP integration tests for the scouting API — the plumbing unit tests can't reach.

Drives the REAL FastAPI app through httpx.ASGITransport against a throwaway SQLite
database, minting REAL JWTs so the auth path is exercised end to end. The Postgres-
only column types (UUID / JSONB / ARRAY) are swapped to SQLite-friendly equivalents
test-side so the same models run unmodified.

Covers the request -> DB -> response path for: session create (server-set analyst
identity), play entry, RBAC (cross-analyst denial, non-reviewer 403, self-review
403, reviewer sign-off flips Gate 2), sessions RLS, analyze (ARRAY + Job), owner
role assignment, and the four report export formats.

Run:  python -m backend.tests.test_api_integration
"""
import os
import uuid
import asyncio
import tempfile
import pathlib
from datetime import datetime

from cryptography.fernet import Fernet

# ── env MUST be set before importing backend.config (imported via models.base) ──
_DB = pathlib.Path(tempfile.gettempdir()) / "coachlenz_itest.db"
if _DB.exists():
    _DB.unlink()
# This suite manages its own throwaway SQLite DB — force it even if an ambient
# DATABASE_URL (e.g. the Postgres one the other tests use) is already set.
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB.as_posix()}"
os.environ.setdefault("SECRET_KEY", "itest-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "itest")
os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())

# Test-only deps (SQLite driver + the web stack). Prod runs Postgres, so aiosqlite
# is not in requirements.txt — install it to run this suite.
try:
    import aiosqlite  # noqa: F401
    import fastapi  # noqa: F401
    import httpx  # noqa: F401
except ImportError as _e:  # pragma: no cover
    raise SystemExit(
        f"Integration test needs test deps (missing: {_e.name}). "
        f"Install with: pip install fastapi aiosqlite httpx"
    )

from sqlalchemy import CHAR, JSON as SAJSON, TypeDecorator  # noqa: E402
from httpx import AsyncClient, ASGITransport  # noqa: E402


class GUID(TypeDecorator):
    """UUID <-> CHAR(36) so the Postgres UUID columns work on SQLite."""
    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else str(value)

    def process_result_value(self, value, dialect):
        return None if value is None else uuid.UUID(str(value))


# Build a SLIM app that mounts the REAL routers under test — this avoids importing
# backend.main, which pulls in every background worker and its heavy deps (boto3,
# twilio, playwright, ...). The routers, services, auth, and DB are all real.
from fastapi import FastAPI  # noqa: E402
from backend.models.base import Base, engine, AsyncSessionLocal  # noqa: E402
from backend.models.organization import Organization  # noqa: E402
from backend.models.user import User  # noqa: E402
from backend.models.game import Game  # noqa: E402
from backend.models.event import Event  # noqa: E402
from backend.models.report import TendencyReport  # noqa: E402
from backend.models.job import Job  # noqa: E402
from backend.models.agent_log import AgentLog  # noqa: E402
from backend.services.auth import hash_password, create_access_token  # noqa: E402
from backend.services.encryption import encrypt_json  # noqa: E402
from backend.routers import scout_football, reports, scout, events  # noqa: E402

app = FastAPI()
app.include_router(scout_football.router)
app.include_router(reports.router)
app.include_router(scout.router)
app.include_router(events.router)


@app.get("/health")
async def _health():
    return {"status": "ok"}


TABLES = [Organization.__table__, User.__table__, Game.__table__,
          Event.__table__, TendencyReport.__table__, Job.__table__, AgentLog.__table__]

# Swap the Postgres-only types on just the tables we create.
for _t in TABLES:
    for _col in _t.columns:
        cls = _col.type.__class__.__name__
        if cls == "UUID":
            _col.type = GUID()
        elif cls == "JSONB":
            _col.type = SAJSON()
        elif cls == "ARRAY":
            _col.type = SAJSON()

ids = {}


async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=TABLES))
    async with AsyncSessionLocal() as db:
        org = Organization(name="Test HS", slug=f"test-{uuid.uuid4().hex[:8]}", is_trial=False)
        db.add(org)
        await db.flush()
        analyst = User(organization_id=org.id, name="Coach Analyst", email="analyst@x.com",
                       hashed_password=hash_password("x"), role="member")
        reviewer = User(organization_id=org.id, name="Coach Reviewer", email="rev@x.com",
                        hashed_password=hash_password("x"), role="owner")
        other = User(organization_id=org.id, name="Other Analyst", email="other@x.com",
                     hashed_password=hash_password("x"), role="member")
        db.add_all([analyst, reviewer, other])
        await db.commit()
        for u in (org, analyst, reviewer, other):
            await db.refresh(u)
        ids["org"] = str(org.id)
        ids["analyst"] = str(analyst.id)
        ids["reviewer"] = str(reviewer.id)
        ids["other"] = str(other.id)
        # A completed report to exercise /export (generated_at set, real summary).
        summary = {
            "total_plays": 80, "offense_plays": 60, "defense_plays": 20,
            "scouting": {
                "report_status": "FINAL",
                "head_coach_priorities": [
                    {"priority": 1, "phase": "DEF", "call": "TAKE AWAY Inside Zone", "confidence": "HIGH"},
                    {"priority": 2, "phase": "OFF", "call": "Attack Cover 3 deep", "confidence": "MEDIUM"},
                ],
                "validation_gates": [{"gate": 6, "name": "Explosive", "passed": False,
                                      "alerts": [{"area": "Run concept", "concept": "Inside Zone", "explosive_rate_pct": 25.0}]}],
            },
            "player_tendencies": {"tracked": True, "by_player": {
                "offense#22": {"jersey": "22", "team": "offense", "roles": {"RB": 10},
                               "touches": 18, "avg_yards": 6.0, "success_rate": 61.0,
                               "explosive_plays": 4, "as_runner": 16, "as_passer_or_receiver": 2,
                               "by_play_type": {"run": 16}}}},
        }
        rpt = TendencyReport(
            organization_id=org.id, game_ids=[str(uuid.uuid4())], sport="football",
            report_type="opponent", title="Export Test Report",
            prose_sections=[
                {"heading": "Executive Summary", "insight_type": "tendency", "body": "Run first."},
                {"heading": "Opponent Offense - Pass Game", "insight_type": "pass", "body": "Verts on 3rd."},
                {"heading": "Opponent Defense - Fronts & Pressure", "insight_type": "defense", "body": "Edge blitz."},
            ],
            summary_json=encrypt_json(summary),
            generated_at=datetime.utcnow(),
        )
        db.add(rpt)
        await db.commit()
        await db.refresh(rpt)
        ids["report"] = str(rpt.id)


def tok(who):
    return {"Authorization": f"Bearer {create_access_token(ids[who], ids['org'])}"}


PASS, FAIL = [], []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


async def run():
    await setup_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://itest") as ac:
        # health (no auth)
        r = await ac.get("/health")
        check("GET /health 200", r.status_code == 200)

        # unauthenticated is rejected
        r = await ac.post("/scout/football/session", json={"opponent": "X"})
        check("session without token -> 401/403", r.status_code in (401, 403))

        # create session as analyst — identity is server-set from the token
        r = await ac.post("/scout/football/session", json={"opponent": "Eagles", "games_scouted": 3}, headers=tok("analyst"))
        check("create session 200", r.status_code == 200)
        sid = r.json().get("session_id")
        check("analyst name server-set (anti-spoof)", r.json().get("analyst") == "Coach Analyst")
        check("session starts as draft", r.json().get("status") == "draft")

        # analyst logs plays
        plays = [{"side": "offense", "game_number": 1, "down": 1, "distance": 10,
                  "formation": "Shotgun", "play_type": "run", "run_concept": "Inside Zone",
                  "yards_gained": 5, "result": "gain", "primary_player_jersey": "22"}]
        r = await ac.post("/scout/football/plays", json={"session_id": sid, "plays": plays}, headers=tok("analyst"))
        check("analyst logs plays 200", r.status_code == 200 and r.json().get("plays_written") == 1)

        # a DIFFERENT plain analyst cannot touch it (RLS)
        r = await ac.post("/scout/football/plays", json={"session_id": sid, "plays": plays}, headers=tok("other"))
        check("cross-analyst play write -> 403", r.status_code == 403)

        # the analyst (role=member) has no review authority
        r = await ac.post("/scout/football/review", json={"session_id": sid, "decision": "reviewed"}, headers=tok("analyst"))
        check("non-reviewer review -> 403", r.status_code == 403)

        # a reviewer (owner) who is NOT the analyst can sign off -> Gate 2 passes
        r = await ac.post("/scout/football/review", json={"session_id": sid, "decision": "final"}, headers=tok("reviewer"))
        check("reviewer sign-off 200 + gate2 passed", r.status_code == 200 and r.json().get("gate2_passed") is True)

        # self-review is blocked: reviewer creates own session, then tries to review it
        r = await ac.post("/scout/football/session", json={"opponent": "Owls"}, headers=tok("reviewer"))
        sid2 = r.json().get("session_id")
        r = await ac.post("/scout/football/review", json={"session_id": sid2, "decision": "reviewed"}, headers=tok("reviewer"))
        check("self-review -> 403", r.status_code == 403)

        # sessions RLS: analyst sees only own; reviewer sees all + can_review
        r = await ac.get("/scout/football/sessions", headers=tok("analyst"))
        an_sessions = r.json().get("sessions", [])
        check("analyst sees only own session", len(an_sessions) == 1 and an_sessions[0]["is_mine"])
        r = await ac.get("/scout/football/sessions", headers=tok("reviewer"))
        rv = r.json()
        check("reviewer sees all sessions + you_can_review", rv.get("you_can_review") is True and len(rv.get("sessions", [])) >= 2)

        # analyze -> queues a report (exercises ARRAY game_ids + Job JSONB payload)
        r = await ac.post("/scout/football/analyze", json={"session_id": sid}, headers=tok("analyst"))
        check("analyze 200 + report_id", r.status_code == 200 and bool(r.json().get("report_id")))

        # analyze with no plays -> 422
        r = await ac.post("/scout/football/analyze", json={"session_id": sid2}, headers=tok("reviewer"))
        check("analyze empty session -> 422", r.status_code == 422)

        # owner assigns a scouting role
        r = await ac.patch("/scout/football/team/role", json={"user_id": ids["other"], "role": "reviewer"}, headers=tok("reviewer"))
        check("owner assigns role 200", r.status_code == 200 and r.json().get("role") == "reviewer")
        # a member cannot assign roles
        r = await ac.patch("/scout/football/team/role", json={"user_id": ids["analyst"], "role": "reviewer"}, headers=tok("analyst"))
        check("member cannot assign role -> 403", r.status_code == 403)

        # ── exports: the four formats ──────────────────────────────────────
        rid = ids["report"]
        r = await ac.get(f"/reports/{rid}/export?format=coordinator", headers=tok("analyst"))
        check("export coordinator 200 (all sections)", r.status_code == 200 and len(r.json()["blocks"]) == 3)
        r = await ac.get(f"/reports/{rid}/export?format=head_coach", headers=tok("analyst"))
        heads = [b["heading"] for b in r.json().get("blocks", [])]
        check("export head_coach one-pager", r.status_code == 200 and any("Explosive" in h for h in heads))
        r = await ac.get(f"/reports/{rid}/export?format=position&unit=DB", headers=tok("analyst"))
        dh = " | ".join(b["heading"] for b in r.json().get("blocks", []))
        check("export position/DB has pass game, not fronts", "Pass Game" in dh and "Fronts" not in dh)
        r = await ac.get(f"/reports/{rid}/export?format=player", headers=tok("analyst"))
        pheads = [b["heading"] for b in r.json().get("blocks", [])]
        check("export player bulletin #22", r.status_code == 200 and any(h.startswith("#22") for h in pheads))
        r = await ac.get(f"/reports/{rid}/export?format=bogus", headers=tok("analyst"))
        check("export bad format -> 422", r.status_code == 422)
        # cross-org / missing report guard
        r = await ac.get(f"/reports/{uuid.uuid4()}/export?format=coordinator", headers=tok("analyst"))
        check("export unknown report -> 404", r.status_code == 404)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILURES:", ", ".join(FAIL))
        raise SystemExit(1)
    print("ALL API INTEGRATION TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(run())
