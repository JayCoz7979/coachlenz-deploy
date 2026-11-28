"""Stage 2 QA on #303 (issue #299), on REAL Postgres with every migration applied.

C1  cross-org: org B gets 404 on every report and live route for org A's ids, no row
    or job is written, and the 404 body is identical to a random id's (no existence
    hint). The reports worker refuses a cross-org job before reading any play, and
    _meta_event never returns another org's session metadata.
H1  POST /reports report_type=live_game is behind the $7 paywall.
M1  two concurrent $7 checkouts for one org create ONE Stripe session; a second paid
    session after the unlock is flagged for refund, once.
M2  migration 069: 'unsubscribed' status on the real table, unsubscribe via SqlLeadStore.

Skipped unless MIGRATIONS_TEST_DATABASE_URL is set (same switch as the 065 tests).
Fictional data only. Stripe is monkeypatched; nothing leaves the machine.
"""
import asyncio
import json
import time
import uuid
from types import SimpleNamespace

import pytest

from backend.tests.test_live_game_report_type_pg import (  # noqa: F401  (pg is a fixture)
    SESSION_BODY, _api, _apply, _consent, _lt_session, _seed, _token, _webhook, needs_pg, pg,
)

pytestmark = [pytest.mark.integration, needs_pg]

RIVAL_SECRET = "Opp Player 10 secret note"


async def _counts(conn):
    return (
        await conn.fetchval("SELECT count(*) FROM tendency_reports"),
        await conn.fetchval("SELECT count(*) FROM jobs"),
        await conn.fetchval("SELECT count(*) FROM events"),
    )


async def _two_orgs(conn):
    await _apply(conn, include_065=True)
    org_a, user_a, live_a = await _seed(conn, "iso-a", plays=4)
    org_b, user_b, live_b = await _seed(conn, "iso-b", plays=4)
    await _consent(conn, org_a, user_a)
    await _consent(conn, org_b, user_b)
    await conn.execute("UPDATE events SET coach_note = $1 WHERE game_id = $2", RIVAL_SECRET, live_a)
    # Not on a trial, so the multi-game probe reaches the ownership check (a trial org
    # gets the upgrade 403 first, which #297 keeps on purpose and leaks nothing).
    await conn.execute("UPDATE organizations SET is_trial = false WHERE id = ANY($1::uuid[])", [org_a, org_b])
    film_a = await conn.fetchval(
        """INSERT INTO games (organization_id, title, sport, status)
           VALUES ($1, 'Film A', 'football', 'ready') RETURNING id""", org_a)
    report_a = await conn.fetchval(
        """INSERT INTO tendency_reports (organization_id, game_ids, sport, report_type, title,
                                         generated_at, share_token)
           VALUES ($1, $2, 'football', 'live_game', 'A Halftime', now(), 'a-share-token') RETURNING id""",
        org_a, [live_a])
    play_a = await conn.fetchval(
        "SELECT id FROM events WHERE game_id = $1 AND event_type = 'play' LIMIT 1", live_a)
    return SimpleNamespace(org_a=org_a, user_a=user_a, live_a=live_a, film_a=film_a, report_a=report_a,
                           play_a=play_a, org_b=org_b, user_b=user_b, live_b=live_b,
                           ta=_token(user_a, org_a), tb=_token(user_b, org_b))


# ── C1: org B gets a 404 on every route for org A's ids ───────────────────────
async def test_cross_org_report_and_live_routes_are_404_with_no_row_and_no_hint(pg):
    w = await _two_orgs(pg)
    missing = str(uuid.uuid4())
    before = await _counts(pg)

    def routes(game, film, report, play):
        return [
            ("POST", "/reports", {"json": {"title": "x", "sport": "football", "game_ids": [game],
                                           "report_type": "live_game"}}),
            ("POST", "/reports", {"json": {"title": "x", "sport": "football", "game_ids": [film],
                                           "report_type": "opponent"}}),
            ("POST", "/reports", {"json": {"title": "x", "sport": "football",
                                           "game_ids": [str(w.live_b), game], "report_type": "custom"}}),
            ("GET", f"/reports/{report}", {}),
            ("POST", f"/reports/{report}/retry", {}),
            ("GET", f"/reports/{report}/export", {}),
            ("GET", f"/reports/{report}/export/csv", {}),
            ("POST", f"/reports/{report}/share", {}),
            ("DELETE", f"/reports/{report}/share", {}),
            ("DELETE", f"/reports/{report}", {}),
            ("GET", f"/live/session/{game}", {}),
            ("POST", "/live/plays", {"json": {"session_id": game, "plays": [{"possession": "us"}]}}),
            ("PATCH", f"/live/play/{play}", {"json": {"yards_gained": 99}}),
            ("DELETE", f"/live/play/{play}", {}),
            ("POST", f"/live/play/{play}/flag", {"json": {"is_coaching_point": True}}),
            ("POST", "/live/report", {"json": {"session_id": game, "scope": "halftime", "period": 3}}),
            ("POST", "/live/report", {"json": {"session_id": game, "scope": "full"}}),
        ]

    real = routes(str(w.live_a), str(w.film_a), str(w.report_a), str(w.play_a))
    fake = routes(missing, missing, missing, missing)
    for (method, path, kw), (_m, fpath, fkw) in zip(real, fake):
        r = await _api(method, path, w.tb, **kw)
        f = await _api(method, fpath, w.tb, **fkw)
        assert r.status_code == 404, (method, path, r.status_code, r.text)
        assert RIVAL_SECRET not in r.text and "A Halftime" not in r.text
        # No existence hint: org A's real id answers exactly like a random one.
        assert f.status_code == 404 and r.json() == f.json(), (method, path, r.text, f.text)

    assert await _counts(pg) == before                        # no report, no job, no play
    assert await pg.fetchval("SELECT share_token FROM tendency_reports WHERE id = $1", w.report_a) == "a-share-token"
    assert await pg.fetchval("SELECT yards_gained FROM events WHERE id = $1", w.play_a) == 4
    sessions_b = (await _api("GET", "/live/sessions", w.tb)).json()["sessions"]
    assert str(w.live_a) not in {s["session_id"] for s in sessions_b}
    listed = (await _api("GET", "/reports", w.tb)).json()
    assert str(w.report_a) not in json.dumps(listed)

    # Positive controls: org A still has everything.
    assert (await _api("GET", f"/live/session/{w.live_a}", w.ta)).status_code == 200
    assert (await _api("GET", f"/reports/{w.report_a}", w.ta)).status_code == 200


async def test_worker_refuses_a_cross_org_job_before_reading_any_play(pg):
    """A row inserted behind the API's back (org B's report naming org A's live game)
    fails with a non-sensitive reason, and no org A play reaches the writer."""
    from unittest.mock import patch
    from backend.workers.worker_reports import GAME_NOT_IN_ORG, ReportInputError, ReportsWorker

    w = await _two_orgs(pg)
    rid = uuid.uuid4()
    await pg.execute(
        """INSERT INTO tendency_reports (id, organization_id, game_ids, sport, report_type, title, params)
           VALUES ($1, $2, $3, 'football', 'live_game', 'Planted', $4::jsonb)""",
        rid, w.org_b, [w.live_a], json.dumps({"scope": "full"}))

    async def must_not_run(*_a, **_k):
        raise AssertionError("cross-org plays must never reach the report writer")

    with patch("backend.services.live_game_report.generate_live_game_sections", new=must_not_run):
        with pytest.raises(ReportInputError):
            await ReportsWorker().handle({"report_id": str(rid)})
    row = await pg.fetchrow("SELECT error_reason, prose_sections, generated_at FROM tendency_reports WHERE id = $1", rid)
    sections = row["prose_sections"]
    sections = json.loads(sections) if isinstance(sections, str) else sections
    assert row["generated_at"] is None and not sections
    assert row["error_reason"] == GAME_NOT_IN_ORG and RIVAL_SECRET not in (row["error_reason"] or "")


async def test_meta_event_never_returns_another_orgs_metadata(pg):
    """_meta_event (live_game.py) is filtered by org: a game_meta row stamped with
    another org on this game id is never read, and its presence cannot 500 the
    session (scalar_one_or_none on two rows)."""
    from backend.models.base import AsyncSessionLocal
    from backend.routers.live_game import META_EVENT_TYPE, _meta_event

    w = await _two_orgs(pg)
    r = await _api("POST", "/live/session", w.ta, json={**SESSION_BODY, "team_name": "Test Team A"})
    assert r.status_code == 200, r.text
    sid = uuid.UUID(r.json()["session_id"])
    await pg.execute(
        """INSERT INTO events (organization_id, game_id, event_type, extra_data)
           VALUES ($1, $2, $3, $4::jsonb)""",
        w.org_b, sid, META_EVENT_TYPE, json.dumps({"team_name": "Rival Team Secret"}))

    async with AsyncSessionLocal() as db:
        mine = await _meta_event(db, sid, w.org_a)
        theirs = await _meta_event(db, sid, w.org_b)
    assert mine is not None and mine.extra_data.get("team_name") == "Test Team A"
    assert theirs is None or theirs.organization_id == w.org_b

    r = await _api("GET", f"/live/session/{sid}", w.ta)
    assert r.status_code == 200, r.text
    assert "Rival Team Secret" not in r.text
    r = await _api("GET", "/live/sessions", w.ta)
    assert r.status_code == 200 and "Rival Team Secret" not in r.text
    assert (await _api("GET", f"/live/session/{sid}", w.tb)).status_code == 404


# ── H1: POST /reports cannot bypass the $7 paywall ────────────────────────────
async def test_unpaid_org_cannot_queue_live_game_via_post_reports(pg):
    await _apply(pg, include_065=True)
    org, user, game = await _seed(pg, "h1-unpaid", plays=4, paid=False)
    token = _token(user, org)
    body = {"title": "Sneaky", "sport": "football", "game_ids": [str(game)], "report_type": "live_game"}
    before = await _counts(pg)

    r = await _api("POST", "/reports", token, json=body)
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "live_tracker_payment_required"
    assert r.json()["detail"]["checkout_url"] == "/live-tracker"
    assert await _counts(pg) == before                        # no report row, no job

    # Other report types are untouched by the $7 gate.
    r = await _api("POST", "/reports", token, json={**body, "report_type": "opponent"})
    assert r.status_code == 200, r.text

    # After a paid test-mode webhook, the same request queues a live_game report.
    r = await _webhook("checkout.session.completed", _lt_session(org, sid="cs_test_h1"), "evt_h1_paid")
    assert r.status_code == 200
    r = await _api("POST", "/reports", token, json=body)
    assert r.status_code == 200, r.text
    assert await pg.fetchval("SELECT report_type FROM tendency_reports WHERE id = $1",
                             uuid.UUID(r.json()["id"])) == "live_game"


# ── M1: two tabs, one Stripe session; extra paid session flagged once ─────────
async def test_two_concurrent_checkouts_create_one_stripe_session(pg, monkeypatch):
    import backend.routers.billing as billing
    from backend.config import settings

    await _apply(pg, include_065=True)
    org, user, _ = await _seed(pg, "m1-tabs", plays=0, paid=False)
    token = _token(user, org)
    monkeypatch.setattr(settings, "STRIPE_PRICE_LIVE_TRACKER", "price_test_live_tracker")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")

    created = []

    def create(**kw):
        created.append(kw)
        n = len(created)
        return SimpleNamespace(id=f"cs_test_tab_{n}", url=f"https://checkout.stripe.test/{n}",
                               expires_at=int(time.time()) + 3600)

    def retrieve(sid):
        return SimpleNamespace(id=sid, status="open", payment_status="unpaid",
                               url=f"https://checkout.stripe.test/{sid.rsplit('_', 1)[-1]}")

    monkeypatch.setattr(billing.stripe.checkout.Session, "create", create)
    monkeypatch.setattr(billing.stripe.checkout.Session, "retrieve", retrieve)
    monkeypatch.setattr(billing.stripe.Customer, "create", lambda **k: SimpleNamespace(id="cus_test_m1"))

    body = {"success_url": "https://app.coachlenz.com/live-tracker/success",
            "cancel_url": "https://app.coachlenz.com/live-tracker?checkout=cancelled"}
    r1, r2 = await asyncio.gather(
        _api("POST", "/billing/live-tracker/checkout", token, json=body),
        _api("POST", "/billing/live-tracker/checkout", token, json=body),
    )
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    assert len(created) == 1                                   # ONE Stripe session
    assert r1.json()["checkout_url"] == r2.json()["checkout_url"] == "https://checkout.stripe.test/1"
    row = await pg.fetchrow(
        "SELECT live_tracker_open_session_id, stripe_customer_id, live_tracker_purchased_at "
        "FROM organizations WHERE id = $1", org)
    assert row["live_tracker_open_session_id"] == "cs_test_tab_1"
    assert row["stripe_customer_id"] == "cus_test_m1"
    assert row["live_tracker_purchased_at"] is None            # checkout never grants

    # The first session is paid: the grant lands and forgets the open session.
    r = await _webhook("checkout.session.completed", _lt_session(org, sid="cs_test_tab_1"), "evt_m1_paid")
    assert r.status_code == 200
    row = await pg.fetchrow("SELECT live_tracker_open_session_id, live_tracker_checkout_session_id "
                            "FROM organizations WHERE id = $1", org)
    assert row["live_tracker_open_session_id"] is None and row["live_tracker_checkout_session_id"] == "cs_test_tab_1"

    # A third tab opened before the grant and was ALSO paid: flagged, never re-granted.
    extra = {**_lt_session(org, sid="cs_test_tab_extra"), "payment_intent": "pi_test_extra",
             "amount_total": 700, "currency": "usd"}
    assert (await _webhook("checkout.session.completed", extra, "evt_m1_extra")).status_code == 200
    assert (await _webhook("checkout.session.completed", extra, "evt_m1_extra")).json()["duplicate"] is True
    assert (await _webhook("checkout.session.async_payment_succeeded", extra, "evt_m1_extra_2")).status_code == 200
    rows = await pg.fetch("SELECT * FROM live_tracker_extra_payments WHERE organization_id = $1", org)
    assert len(rows) == 1
    assert rows[0]["checkout_session_id"] == "cs_test_tab_extra" and rows[0]["needs_refund"] is True
    assert rows[0]["payment_intent_id"] == "pi_test_extra" and rows[0]["amount_total"] == 700
    assert await pg.fetchval("SELECT live_tracker_checkout_session_id FROM organizations WHERE id = $1",
                             org) == "cs_test_tab_1"

    # And the endpoint now refuses a new checkout outright.
    r = await _api("POST", "/billing/live-tracker/checkout", token, json=body)
    assert r.status_code == 409 and len(created) == 1


# ── M2: 069 on the real table ─────────────────────────────────────────────────
async def test_069_allows_unsubscribed_and_sql_store_unsubscribes(pg):
    import asyncpg
    from backend.models.base import AsyncSessionLocal
    from backend.services import halftime_leads as svc

    await _apply(pg, include_065=True)
    lead_id = await pg.fetchval(
        """INSERT INTO halftime_pdf_leads (name, email, status, consent_text)
           VALUES ('Test Coach', 'qa.coach@example.com', 'confirmed', 'v1') RETURNING id""")
    with pytest.raises(asyncpg.CheckViolationError):
        await pg.execute("UPDATE halftime_pdf_leads SET status = 'junk' WHERE id = $1", lead_id)

    async with AsyncSessionLocal() as db:
        out = await svc.unsubscribe_lead(svc.SqlLeadStore(db), token=svc.unsubscribe_token(lead_id))
    assert out["status"] == "unsubscribed"
    row = await pg.fetchrow("SELECT status, unsubscribed_at, token_hash FROM halftime_pdf_leads WHERE id = $1", lead_id)
    assert row["status"] == "unsubscribed" and row["unsubscribed_at"] is not None and row["token_hash"] is None

    # Through the real app, one-click form POST from the List-Unsubscribe header.
    r = await _api("POST", f"/leads/halftime-sheet/unsubscribe?token={svc.unsubscribe_token(lead_id)}",
                   content="List-Unsubscribe=One-Click",
                   headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200 and r.json()["status"] == "unsubscribed"
    r = await _api("POST", "/leads/halftime-sheet/unsubscribe",
                   json={"token": svc.unsubscribe_token(uuid.uuid4())})
    assert r.status_code == 200                                # unknown lead: same idempotent answer
