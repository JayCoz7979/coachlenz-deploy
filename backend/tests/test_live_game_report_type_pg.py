"""Real-Postgres tests for tendency_reports.report_type 'live_game'.

Skipped unless MIGRATIONS_TEST_DATABASE_URL is set. Fails (does not skip) when
REQUIRE_PG_MIGRATION_TESTS=1 and that URL is missing.

The migration runner (backend/migrate.py) globs backend/migrations/*.sql only,
and records each applied file in schema_migrations.filename. The down script
lives in backend/migrations/down/ and is never applied by the runner.
"""
import json
import os
import uuid
from unittest.mock import patch

import pytest

_URL = os.environ.get("MIGRATIONS_TEST_DATABASE_URL")
_REQUIRE = os.environ.get("REQUIRE_PG_MIGRATION_TESTS") == "1"

needs_pg = pytest.mark.skipif(not _URL, reason="MIGRATIONS_TEST_DATABASE_URL is not set")


@pytest.mark.integration
def test_require_pg_migration_tests_fails_when_url_missing():
    if _REQUIRE and not _URL:
        pytest.fail(
            "REQUIRE_PG_MIGRATION_TESTS=1 but MIGRATIONS_TEST_DATABASE_URL is not set"
        )
    if not _URL:
        pytest.skip("MIGRATIONS_TEST_DATABASE_URL is not set")


@pytest.mark.unit
def test_runner_glob_ignores_down_folder():
    """The runner's glob is not recursive, so the down script is never applied."""
    from backend.migrate import MIGRATIONS_DIR

    top = list(MIGRATIONS_DIR.glob("*.sql"))
    assert top, "expected migration files"
    assert all(p.parent == MIGRATIONS_DIR for p in top)
    assert not any(p.name.endswith(".down.sql") for p in top)
    assert any(p.name == "065_live_game_report_type.sql" for p in top)
    down = MIGRATIONS_DIR / "down" / "065_live_game_report_type.down.sql"
    assert down.is_file()
    # A recursive glob would see it. The runner does not use one.
    assert any(p.name.endswith(".down.sql") for p in MIGRATIONS_DIR.rglob("*.sql"))


def _norm(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://").rstrip("/")


def _same_database():
    db = os.environ.get("DATABASE_URL", "")
    mig = os.environ.get("MIGRATIONS_TEST_DATABASE_URL", "")
    assert _norm(db) == _norm(mig), (
        "DATABASE_URL and MIGRATIONS_TEST_DATABASE_URL must be the same database. "
        "The app and the migration runner read DATABASE_URL. These tests inspect "
        "MIGRATIONS_TEST_DATABASE_URL."
    )


async def _reset(conn):
    await conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
    await conn.execute("CREATE SCHEMA public")
    await conn.execute("GRANT ALL ON SCHEMA public TO postgres")
    await conn.execute("GRANT ALL ON SCHEMA public TO public")


async def _apply(conn, include_065: bool):
    from backend.migrate import MIGRATIONS_DIR

    await conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
    )
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    for f in files:
        if not include_065 and f.name == "065_live_game_report_type.sql":
            continue
        await conn.execute(f.read_text(encoding="utf-8"))
        await conn.execute(
            "INSERT INTO schema_migrations(filename) VALUES($1) ON CONFLICT DO NOTHING",
            f.name,
        )


async def _constraint(conn) -> str:
    return await conn.fetchval(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'tendency_reports_report_type_check'"
    ) or ""


async def _seed(conn, slug: str, plays: int, quarter: int = 1, yards=4, paid: bool = True):
    # The logger is the $7 Live Tracker unlock (migration 066). Report-path tests
    # seed a paid org; the gate tests below seed paid=False explicitly.
    org = await conn.fetchval(
        "INSERT INTO organizations (name, slug, live_tracker_purchased_at) "
        "VALUES ($1, $2, CASE WHEN $3 THEN now() END) RETURNING id",
        "Logger Org", slug, paid,
    )
    user = await conn.fetchval(
        """INSERT INTO users (organization_id, name, email, hashed_password, role)
           VALUES ($1, 'Coach', $2, 'not-a-real-hash', 'owner') RETURNING id""",
        org, f"{slug}@example.com",
    )
    game = await conn.fetchval(
        """INSERT INTO games (organization_id, title, sport, opponent, status)
           VALUES ($1, 'Friday', 'football', 'Rivals', 'live') RETURNING id""",
        org,
    )
    for _ in range(plays):
        await conn.execute(
            """INSERT INTO events
               (organization_id, game_id, event_type, side, play_type, yards_gained, extra_data)
               VALUES ($1, $2, 'play', 'offense', 'Run', $3, $4::jsonb)""",
            org, game, yards, json.dumps({"quarter": quarter, "possession": "us"}),
        )
    return org, user, game


def _token(user, org) -> str:
    from backend.services.auth import create_access_token
    return create_access_token(str(user), str(org))


async def _post_report(session_id, token, scope, period=None):
    body = {"session_id": str(session_id), "scope": scope}
    if period is not None:
        body["period"] = period
    return await _api("POST", "/live/report", token, json=body)


async def _api(method, path, token=None, **kw):
    import httpx
    from backend.main import app

    headers = dict(kw.pop("headers", {}) or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, headers=headers, **kw)


def _sections(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


def _arm_fernet():
    from cryptography.fernet import Fernet
    from backend.config import settings
    if not settings.FERNET_KEY:
        settings.FERNET_KEY = Fernet.generate_key().decode()


@pytest.fixture
async def pg():
    import asyncpg
    from backend.models.base import engine

    _same_database()
    await engine.dispose()
    conn = await asyncpg.connect(_URL)
    await _reset(conn)
    try:
        yield conn
    finally:
        await conn.close()
        await engine.dispose()


# ── (a) without 065 the insert and the route both fail ──────────────────────
@pytest.mark.integration
@needs_pg
async def test_without_065_live_game_insert_and_route_fail(pg):
    import asyncpg

    await _apply(pg, include_065=False)
    defn = await _constraint(pg)
    assert "live_game" not in defn
    assert "opponent" in defn and "self_scout" in defn and "custom" in defn

    org, user, game = await _seed(pg, "no065", plays=4)
    with pytest.raises(asyncpg.CheckViolationError) as ei:
        await pg.execute(
            """INSERT INTO tendency_reports (organization_id, game_ids, sport, report_type, title)
               VALUES ($1, $2, 'football', 'live_game', 'Halftime')""",
            org, [game],
        )
    assert "tendency_reports_report_type_check" in str(ei.value)
    # The three historical types still insert.
    await pg.execute(
        """INSERT INTO tendency_reports (organization_id, game_ids, sport, report_type, title)
           VALUES ($1, $2, 'football', 'opponent', 'Opp')""",
        org, [game],
    )

    # Enough plays that the thin-data guard is not what rejects the request.
    resp = await _post_report(game, _token(user, org), "full")
    assert resp.status_code == 500, resp.text
    assert "Traceback" not in resp.text
    assert await pg.fetchval(
        "SELECT count(*) FROM tendency_reports WHERE report_type = 'live_game'"
    ) == 0


# ── (b) 065 allows the four types, rejects junk, and is a no-op when re-run ─
@pytest.mark.integration
@needs_pg
async def test_065_allows_four_types_rejects_junk_and_is_idempotent(pg):
    import asyncpg
    from backend.migrate import MIGRATIONS_DIR

    await _apply(pg, include_065=True)
    org, _user, game = await _seed(pg, "yes065", plays=0)
    for report_type in ("opponent", "self_scout", "custom", "live_game"):
        await pg.execute(
            """INSERT INTO tendency_reports (organization_id, game_ids, sport, report_type, title)
               VALUES ($1, $2, 'football', $3, $4)""",
            org, [game], report_type, report_type,
        )
    with pytest.raises(asyncpg.CheckViolationError) as ei:
        await pg.execute(
            """INSERT INTO tendency_reports (organization_id, game_ids, sport, report_type, title)
               VALUES ($1, $2, 'football', 'not_a_type', 'Junk')""",
            org, [game],
        )
    assert "tendency_reports_report_type_check" in str(ei.value)

    sql = (MIGRATIONS_DIR / "065_live_game_report_type.sql").read_text(encoding="utf-8")
    await pg.execute(sql)
    await pg.execute(sql)
    defn = await _constraint(pg)
    for report_type in ("opponent", "self_scout", "custom", "live_game"):
        assert report_type in defn
    with pytest.raises(asyncpg.CheckViolationError):
        await pg.execute(
            """INSERT INTO tendency_reports (organization_id, game_ids, sport, report_type, title)
               VALUES ($1, $2, 'football', 'still_junk', 'Junk 2')""",
            org, [game],
        )


# ── (c) the runner applies 065 and never the down file ──────────────────────
@pytest.mark.integration
@needs_pg
async def test_runner_applies_065_and_never_the_down_file(pg):
    from backend.migrate import run as migrate_run

    await migrate_run()
    names = {r["filename"] for r in await pg.fetch("SELECT filename FROM schema_migrations")}
    assert "065_live_game_report_type.sql" in names
    assert "065_live_game_report_type.down.sql" not in names
    assert not any(name.endswith(".down.sql") for name in names)
    col = await pg.fetchval(
        """SELECT column_name FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'schema_migrations'
             AND column_name = 'filename'"""
    )
    assert col == "filename"
    assert "live_game" in await _constraint(pg)


# ── (d) down refuses while rows exist, then restores, and is safe twice ─────
@pytest.mark.integration
@needs_pg
async def test_down_refuses_then_restores_and_runner_reapplies(pg):
    import asyncpg
    from backend.migrate import MIGRATIONS_DIR, run as migrate_run

    await migrate_run()
    org, _user, game = await _seed(pg, "down065", plays=0)
    await pg.execute(
        """INSERT INTO tendency_reports (organization_id, game_ids, sport, report_type, title)
           VALUES ($1, $2, 'football', 'live_game', 'Keep me')""",
        org, [game],
    )
    down_sql = (MIGRATIONS_DIR / "down" / "065_live_game_report_type.down.sql").read_text(encoding="utf-8")

    with pytest.raises(asyncpg.PostgresError) as ei:
        await pg.execute(down_sql)
    assert "065 down refused:" in str(ei.value)
    assert "Nothing was changed." in str(ei.value)
    try:
        await pg.execute("ROLLBACK")
    except Exception:
        pass
    assert "live_game" in await _constraint(pg)
    assert await pg.fetchval(
        "SELECT count(*) FROM tendency_reports WHERE report_type = 'live_game'"
    ) == 1
    assert await pg.fetchval(
        "SELECT count(*) FROM schema_migrations WHERE filename = '065_live_game_report_type.sql'"
    ) == 1

    await pg.execute("DELETE FROM tendency_reports WHERE report_type = 'live_game'")
    await pg.execute(down_sql)
    defn = await _constraint(pg)
    assert "live_game" not in defn
    assert "opponent" in defn and "self_scout" in defn and "custom" in defn
    assert await pg.fetchval(
        "SELECT count(*) FROM schema_migrations WHERE filename = '065_live_game_report_type.sql'"
    ) == 0

    # Second run: no live_game rows, same constraint, delete matches nothing.
    await pg.execute(down_sql)
    assert "live_game" not in await _constraint(pg)

    await migrate_run()
    assert await pg.fetchval(
        "SELECT count(*) FROM schema_migrations WHERE filename = '065_live_game_report_type.sql'"
    ) == 1
    assert "live_game" in await _constraint(pg)
    await pg.execute(
        """INSERT INTO tendency_reports (organization_id, game_ids, sport, report_type, title)
           VALUES ($1, $2, 'football', 'live_game', 'After reapply')""",
        org, [game],
    )


# ── (e) route 200 for this_half and full, then the real worker completes ────
@pytest.mark.integration
@needs_pg
async def test_route_queues_live_game_and_worker_completes(pg):
    from backend.workers.worker_reports import ReportsWorker

    await _apply(pg, include_065=True)
    _arm_fernet()
    org, user, game = await _seed(pg, "full065", plays=4, quarter=1)
    token = _token(user, org)

    seen = []

    async def fake_sections(sport, events, params, tendency_summary, is_trial=False,
                            season_events=None, prior_game_count=0):
        seen.append({
            "sport": sport,
            "plays": len([e for e in events if getattr(e, "event_type", None) == "play"]),
            "scope": (params or {}).get("scope"),
        })
        return [{"heading": "Mocked", "insight_type": "tendency", "body": "mocked section"}]

    for scope in ("this_half", "full"):
        resp = await _post_report(game, token, scope, period=1)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "queued"
        assert body["scope"] == scope
        assert body["plays"] == 4

    rows = await pg.fetch(
        """SELECT id::text AS id, report_type, params
           FROM tendency_reports WHERE organization_id = $1 ORDER BY created_at""",
        org,
    )
    assert len(rows) == 2
    assert {r["report_type"] for r in rows} == {"live_game"}
    scopes = set()
    for r in rows:
        params = r["params"] if isinstance(r["params"], dict) else json.loads(r["params"])
        scopes.add(params["scope"])
    assert scopes == {"this_half", "full"}

    jobs = await pg.fetch(
        "SELECT payload FROM jobs WHERE organization_id = $1 AND job_type = 'report'",
        org,
    )
    assert len(jobs) == 2

    with patch("backend.services.live_game_report.generate_live_game_sections", new=fake_sections):
        for row in rows:
            result = await ReportsWorker().handle({"report_id": row["id"]})
            assert result["sections"] == 1
            stored = await pg.fetchrow(
                "SELECT prose_sections, generated_at, error_reason FROM tendency_reports WHERE id = $1",
                uuid.UUID(row["id"]),
            )
            sections = _sections(stored["prose_sections"])
            assert sections[0]["body"] == "mocked section"
            assert stored["generated_at"] is not None
            assert stored["error_reason"] is None

    assert {item["scope"] for item in seen} == {"this_half", "full"}
    assert all(item["plays"] == 4 and item["sport"] == "football" for item in seen)


# ── Part B: thin logs do not call the model. The route says why. ────────────
@pytest.mark.integration
@needs_pg
@pytest.mark.parametrize("plays,expected", [
    (0, "No plays logged for this part of the game yet."),
    (1, "Not enough plays logged yet for a full report. Log a few more plays and try again."),
    (2, "Not enough plays logged yet for a full report. Log a few more plays and try again."),
])
async def test_route_refuses_thin_scope_without_a_report(pg, plays, expected):
    from backend.services.live_game_report import EMPTY_SCOPE_MESSAGE, THIN_PLAYS_MESSAGE

    assert expected in (EMPTY_SCOPE_MESSAGE, THIN_PLAYS_MESSAGE)
    await _apply(pg, include_065=True)
    org, user, game = await _seed(pg, f"thin{plays}", plays=plays)
    resp = await _post_report(game, _token(user, org), "full")
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == expected
    assert await pg.fetchval(
        "SELECT count(*) FROM tendency_reports WHERE organization_id = $1", org
    ) == 0
    assert await pg.fetchval(
        "SELECT count(*) FROM jobs WHERE organization_id = $1", org
    ) == 0


@pytest.mark.integration
@needs_pg
async def test_route_zero_plays_in_first_half(pg):
    from backend.services.live_game_report import EMPTY_SCOPE_MESSAGE

    await _apply(pg, include_065=True)
    org, user, game = await _seed(pg, "q3half", plays=4, quarter=3)
    resp = await _post_report(game, _token(user, org), "this_half", period=1)
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == EMPTY_SCOPE_MESSAGE
    assert await pg.fetchval(
        "SELECT count(*) FROM tendency_reports WHERE organization_id = $1", org
    ) == 0


@pytest.mark.integration
@needs_pg
@pytest.mark.parametrize("plays", [1, 2])
async def test_worker_one_and_two_plays_skip_the_ai_writer(pg, plays):
    from backend.services.live_game_report import THIN_PLAYS_MESSAGE
    from backend.workers.worker_reports import ReportsWorker

    await _apply(pg, include_065=True)
    _arm_fernet()
    org, _user, game = await _seed(pg, f"work{plays}", plays=plays, yards=None)
    report_id = uuid.uuid4()
    await pg.execute(
        """INSERT INTO tendency_reports
           (id, organization_id, game_ids, sport, report_type, title, params)
           VALUES ($1, $2, $3, 'football', 'live_game', $4, $5::jsonb)""",
        report_id, org, [game], f"{plays} play report",
        json.dumps({"scope": "full", "label": "Full Game"}),
    )

    called = {"n": 0}

    async def boom(*_args, **_kwargs):
        called["n"] += 1
        raise AssertionError("AI writer must not be called for a thin live report")

    with patch("backend.services.live_game_report.client.messages.create", new=boom):
        result = await ReportsWorker().handle({"report_id": str(report_id)})

    assert called["n"] == 0
    assert result["sections"] == 1
    stored = await pg.fetchrow(
        "SELECT prose_sections, generated_at, error_reason FROM tendency_reports WHERE id = $1",
        report_id,
    )
    sections = _sections(stored["prose_sections"])
    assert sections[0]["body"] == THIN_PLAYS_MESSAGE
    assert "Not Enough Plays" in sections[0]["heading"]
    assert stored["generated_at"] is not None
    assert stored["error_reason"] is None


# ── Halftime Sheet scope on a database that has the check constraint ────────
async def _seed_plays(conn, org, game, quarters):
    for q in quarters:
        await conn.execute(
            """INSERT INTO events
               (organization_id, game_id, event_type, side, play_type, yards_gained, extra_data)
               VALUES ($1, $2, 'play', 'offense', 'Run', 4, $3::jsonb)""",
            org, game, json.dumps({"quarter": q, "possession": "us"}),
        )


@pytest.mark.integration
@needs_pg
async def test_halftime_scope_queues_live_game_report_from_first_half_plays(pg):
    await _apply(pg, include_065=True)
    org, user, game = await _seed(pg, "half3", plays=0)
    await _seed_plays(pg, org, game, [1, 1, 2, 3, 3])
    resp = await _post_report(game, _token(user, org), "halftime", period=3)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scope"] == "halftime" and body["plays"] == 3    # Q3 plays excluded
    row = await pg.fetchrow(
        "SELECT report_type, title, params FROM tendency_reports WHERE organization_id = $1", org)
    assert row["report_type"] == "live_game"
    params = row["params"] if isinstance(row["params"], dict) else json.loads(row["params"])
    assert params["scope"] == "halftime" and params["event_filter"] == {"max_quarter": 2}
    assert row["title"].startswith("Halftime Report")


@pytest.mark.integration
@needs_pg
async def test_halftime_scope_with_only_second_half_plays_is_422_and_writes_nothing(pg):
    from backend.services.live_game_report import EMPTY_SCOPE_MESSAGE

    await _apply(pg, include_065=True)
    org, user, game = await _seed(pg, "half0", plays=4, quarter=3)
    resp = await _post_report(game, _token(user, org), "halftime", period=3)
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == EMPTY_SCOPE_MESSAGE
    assert await pg.fetchval("SELECT count(*) FROM tendency_reports WHERE organization_id = $1", org) == 0
    assert await pg.fetchval("SELECT count(*) FROM jobs WHERE organization_id = $1", org) == 0


# ── $7 Live Tracker: real gate + real webhook grant on Postgres ──────────────
def _signed_event(event_type, obj, event_id):
    import hashlib
    import hmac
    import time
    from backend.config import settings

    body = json.dumps({"id": event_id, "object": "event", "type": event_type, "data": {"object": obj}})
    ts = int(time.time())
    sig = hmac.new(settings.STRIPE_WEBHOOK_SECRET.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return body, f"t={ts},v1={sig}"


def _lt_session(org, payment_status="paid", sid="cs_test_pg"):
    return {"id": sid, "object": "checkout.session", "mode": "payment",
            "payment_status": payment_status, "customer": "cus_pg",
            "metadata": {"org_id": str(org), "kind": "live_tracker"}}


async def _webhook(event_type, obj, event_id):
    body, header = _signed_event(event_type, obj, event_id)
    return await _api("POST", "/billing/webhook", content=body,
                      headers={"stripe-signature": header, "content-type": "application/json"})


async def _consent(conn, org, user):
    from backend.services.legal import DOCUMENT_VERSIONS
    await conn.execute(
        "INSERT INTO legal_acceptances (organization_id, user_id, document, version) VALUES ($1, $2, 'student_data', $3)",
        org, user, DOCUMENT_VERSIONS["student_data"],
    )


SESSION_BODY = {"sport": "football", "team_name": "Us", "opponent": "Rivals"}


@pytest.mark.integration
@needs_pg
async def test_unpaid_org_cannot_start_or_resume_a_live_session(pg):
    await _apply(pg, include_065=True)
    org, user, game = await _seed(pg, "unpaid", plays=4, paid=False)
    await _consent(pg, org, user)
    token = _token(user, org)
    origin = "https://app.coachlenz.com"

    r = await _api("POST", "/live/session", token, json=SESSION_BODY, headers={"Origin": origin})
    assert r.status_code == 403, r.text
    assert "$7 one-time" in r.json()["detail"]
    assert r.headers.get("x-coachlenz-locked") == "live_tracker"
    assert r.headers.get("access-control-allow-origin") == origin          # JSON + CORS
    for method, path, kw in (
        ("GET", f"/live/session/{game}", {}),
        ("POST", "/live/plays", {"json": {"session_id": str(game), "plays": [{"possession": "us"}]}}),
        ("POST", "/live/report", {"json": {"session_id": str(game), "scope": "halftime"}}),
    ):
        r = await _api(method, path, token, **kw)
        assert r.status_code == 403, (path, r.text)
    assert await pg.fetchval("SELECT count(*) FROM games WHERE organization_id = $1", org) == 1
    assert await pg.fetchval("SELECT count(*) FROM tendency_reports WHERE organization_id = $1", org) == 0

    access = await _api("GET", "/live/access", token)
    assert access.status_code == 200 and access.json()["has_access"] is False


@pytest.mark.integration
@needs_pg
async def test_paid_webhook_grants_once_then_the_coach_can_log(pg):
    await _apply(pg, include_065=True)
    org, user, _game = await _seed(pg, "buyer", plays=0, paid=False)
    await _consent(pg, org, user)
    token = _token(user, org)

    # A completed-but-unpaid session (delayed method) and an expired one grant nothing.
    r = await _webhook("checkout.session.completed", _lt_session(org, "unpaid"), "evt_pg_unpaid")
    assert r.status_code == 200, r.text
    r = await _webhook("checkout.session.expired", _lt_session(org, "unpaid"), "evt_pg_expired")
    assert r.status_code == 200, r.text
    assert await pg.fetchval("SELECT live_tracker_purchased_at FROM organizations WHERE id = $1", org) is None
    assert (await _api("POST", "/live/session", token, json=SESSION_BODY)).status_code == 403

    # Bad signature: 400, nothing recorded.
    body, header = _signed_event("checkout.session.completed", _lt_session(org), "evt_pg_forged")
    r = await _api("POST", "/billing/webhook", content=body,
                   headers={"stripe-signature": header.replace("v1=", "v1=00"), "content-type": "application/json"})
    assert r.status_code == 400
    assert await pg.fetchval("SELECT live_tracker_purchased_at FROM organizations WHERE id = $1", org) is None

    # Paid: granted.
    r = await _webhook("checkout.session.completed", _lt_session(org), "evt_pg_paid")
    assert r.status_code == 200 and r.json() == {"received": True}
    first = await pg.fetchrow(
        "SELECT live_tracker_purchased_at, live_tracker_checkout_session_id, subscription_tier, is_trial "
        "FROM organizations WHERE id = $1", org)
    assert first["live_tracker_purchased_at"] is not None
    assert first["live_tracker_checkout_session_id"] == "cs_test_pg"

    # Redelivery of the same event, and a second paid event, change nothing.
    r = await _webhook("checkout.session.completed", _lt_session(org), "evt_pg_paid")
    assert r.json() == {"received": True, "duplicate": True}
    r = await _webhook("checkout.session.async_payment_succeeded", _lt_session(org, sid="cs_test_pg_2"), "evt_pg_paid_2")
    assert r.status_code == 200
    again = await pg.fetchrow(
        "SELECT live_tracker_purchased_at, live_tracker_checkout_session_id, subscription_tier, is_trial "
        "FROM organizations WHERE id = $1", org)
    assert again["live_tracker_purchased_at"] == first["live_tracker_purchased_at"]
    assert again["live_tracker_checkout_session_id"] == "cs_test_pg"
    # The $7 unlock is not a subscription and touches no plan fields.
    assert again["subscription_tier"] == first["subscription_tier"]
    assert again["is_trial"] == first["is_trial"]

    # Paid coach: start, log, resume, undo, report.
    r = await _api("POST", "/live/session", token, json=SESSION_BODY)
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    plays = [{"possession": "us", "quarter": 1, "play_type": "Run", "yards_gained": 4, "client_uid": f"u{i}"}
             for i in range(4)]
    r = await _api("POST", "/live/plays", token, json={"session_id": sid, "plays": plays})
    assert r.status_code == 200 and r.json()["plays_written"] == 4
    r = await _api("GET", f"/live/session/{sid}", token)
    assert r.status_code == 200 and len(r.json()["plays"]) == 4
    last = r.json()["plays"][-1]["event_id"]
    assert (await _api("DELETE", f"/live/play/{last}", token)).status_code == 200
    r = await _post_report(sid, token, "halftime", period=2)
    assert r.status_code == 200, r.text
    assert r.json()["plays"] == 3
