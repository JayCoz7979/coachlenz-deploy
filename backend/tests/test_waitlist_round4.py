"""Round 4 QA fix: every marketing lead has a usable unsubscribe token.

* Migration 061 backfills null or blank lead tokens (43-char URL-safe) and
  records the rows so its down can undo exactly those.
* A repeat signup fills a missing token and never replaces a valid one.
* With no usable token anyway, a send carries no List-Unsubscribe header and
  the reply-to-unsubscribe footer, and the live gateway refuses any body or
  header holding a link that ends in "token=".
No test talks to Resend.
"""
import asyncio
import json
import os
import pathlib
import subprocess
import sys
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

from backend.config import settings
from backend.services import waitlist_email as mail
from backend.services.unsubscribe_token import is_valid_unsubscribe_token
from backend.services.waitlist_capture import (
    apply_repeat,
    ensure_unsubscribe_token,
    new_lead_kwargs,
    new_unsubscribe_token,
)

MIG = pathlib.Path(__file__).resolve().parents[1] / "migrations"
UP = MIG / "061_marketing_lead_unsubscribe_token.sql"
DOWN = MIG / "061_marketing_lead_unsubscribe_token.down.sql"
VALID = "unsub-tok-0123456789abcdefghijklmnopqrstuvw"


def _lead(**kw):
    base = dict(
        id="lead-1", email="Coach@School.edu", role="head_coach", role_branch="coach",
        school="Lincoln", sport="basketball", source="coachlenz-app-waitlist",
        first_name="Pat", lead_magnet="halftime-sheet-v1", utm_source=None, utm_medium=None,
        utm_campaign=None, utm_content=None, utm_term=None, referrer=None, landing_path=None,
        ref_code=None, created_at=datetime(2026, 11, 1, 12, 0, 0), confirmed_at=None,
        confirm_sent_at=None, confirm_token_hash=None, unsubscribed_at=None,
        reminder_sent_at=None, a1_sent_at=None, l1m_sent_at=None,
        unsubscribe_token=VALID, has_account=False, consent_text_version="v1",
        marketing_consent=True,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _body(**kw):
    base = dict(role="head_coach", first_name="Pat", school=None, sport=None, lead_magnet=None,
                utm_source=None, utm_medium=None, utm_campaign=None, utm_content=None,
                utm_term=None, referrer=None, landing_path=None, ref_code=None)
    base.update(kw)
    return SimpleNamespace(**base)


class _Recorder:
    def __init__(self):
        self.sends = []

    def send(self, payload):
        self.sends.append(payload)
        return {"id": "msg-1"}

    def __getattr__(self, name):
        return lambda *a, **k: None


class _DB:
    def add(self, obj):
        pass


@pytest.fixture
def email_on(monkeypatch):
    monkeypatch.setattr(settings, "WAITLIST_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "PUBLIC_APP_URL", "https://app.coachlenz.com")
    monkeypatch.delenv("WAITLIST_FROM", raising=False)
    gw = _Recorder()
    mail.set_gateway(gw)
    yield gw
    mail.set_gateway(None)


# ---------- one generator, repeat signups ----------

@pytest.mark.unit
def test_new_leads_and_the_generator_make_the_43_char_urlsafe_shape():
    for token in (new_unsubscribe_token(), new_lead_kwargs("a@b.co", "x", _body())["unsubscribe_token"]):
        assert len(token) == 43 and is_valid_unsubscribe_token(token)


@pytest.mark.unit
@pytest.mark.parametrize("missing", [None, "", "   ", "abc", "bad token!"])
def test_repeat_signup_sets_a_token_when_it_is_missing_or_unusable(missing):
    row = _lead(unsubscribe_token=missing)
    apply_repeat(row, _body(), "coachlenz-app-waitlist")
    assert len(row.unsubscribe_token) == 43 and is_valid_unsubscribe_token(row.unsubscribe_token)


@pytest.mark.unit
@pytest.mark.parametrize("existing", [VALID, uuid.uuid4().hex])
def test_repeat_signup_never_replaces_a_valid_token(existing):
    row = _lead(unsubscribe_token=existing)
    apply_repeat(row, _body(school="Central"), "coachlenz-app-waitlist")
    assert row.unsubscribe_token == existing
    assert ensure_unsubscribe_token(row) is False


# ---------- no usable token: no header, no footer link, gateway refuses ----------

@pytest.mark.unit
@pytest.mark.parametrize("bad", ["", None, "abc"])
def test_headers_are_left_out_without_a_usable_token(bad):
    assert mail._headers(bad or "") == {}
    footer = mail.standard_footer(bad)
    assert "token=" not in footer
    assert "with the word unsubscribe" in footer


@pytest.mark.unit
def test_headers_still_carry_one_click_with_a_valid_token(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_APP_URL", "https://app.coachlenz.com")
    h = mail._headers(VALID)
    assert h["List-Unsubscribe"].startswith(f"<https://app.coachlenz.com/unsubscribe/one-click?token={VALID}>")
    assert h["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


@pytest.mark.unit
@pytest.mark.parametrize("missing", [None, ""])
def test_marketing_sends_for_a_tokenless_lead_carry_no_dead_link(email_on, missing):
    gw = email_on
    lead = _lead(unsubscribe_token=missing, confirmed_at=datetime(2026, 11, 2))
    assert asyncio.run(mail.send_nurture_step(_DB(), lead)) == "sent"
    sent = gw.sends[-1]
    assert "List-Unsubscribe" not in sent["headers"]
    assert "List-Unsubscribe-Post" not in sent["headers"]
    assert "token=" not in sent["text"]
    assert "with the word unsubscribe" in sent["text"]
    mail.refuse_if_tokenless_unsubscribe(sent)  # nothing to refuse


@pytest.mark.unit
@pytest.mark.parametrize("payload", [
    {"text": "Unsubscribe: https://app.coachlenz.com/unsubscribe?token=\nThanks"},
    {"text": "Unsubscribe: https://app.coachlenz.com/unsubscribe?token="},
    {"text": "ok", "headers": {"List-Unsubscribe": "<https://app.coachlenz.com/unsubscribe/one-click?token=>"}},
    {"text": "ok", "html": '<a href="https://app.coachlenz.com/unsubscribe?token=">x</a>'},
])
def test_gateway_refuses_a_link_with_an_empty_token(payload):
    with pytest.raises(RuntimeError, match="empty token"):
        mail.refuse_if_tokenless_unsubscribe(payload)


@pytest.mark.unit
def test_live_send_refuses_before_the_resend_sdk(monkeypatch):
    monkeypatch.setattr(settings, "WAITLIST_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_not_real")
    monkeypatch.setattr(settings, "WAITLIST_RESEND_TOPIC_ID", "topic-1")
    monkeypatch.setattr(settings, "WAITLIST_RESEND_SEGMENT_IDS",
                        json.dumps({name: f"seg-{i}" for i, name in enumerate(mail.ALL_SEGMENTS)}))
    monkeypatch.setitem(sys.modules, "resend", None)  # importing it would fail the test
    gw = mail.ResendGateway()
    if mail.resend_config_missing():
        pytest.skip("this build needs more config to reach send")
    with pytest.raises(RuntimeError, match="empty token"):
        gw.send({"to": "qa+x@coachlenz.com", "text": "hi",
                 "headers": {"List-Unsubscribe": "<https://app.coachlenz.com/unsubscribe/one-click?token=>"}})


@pytest.mark.unit
def test_gateway_lets_a_real_link_through():
    mail.refuse_if_tokenless_unsubscribe({
        "text": f"https://app.coachlenz.com/unsubscribe?token={VALID}\n",
        "headers": mail._headers(VALID) or {"List-Unsubscribe": f"<x/unsubscribe/one-click?token={VALID}>"},
    })


# ---------- migration 061 (SQL shape) ----------

def _body_sql(path):
    return "\n".join(l for l in path.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("--"))


@pytest.mark.unit
def test_061_only_fills_null_or_blank_tokens_and_records_them():
    sql = _body_sql(UP)
    assert "WHERE unsubscribe_token IS NULL OR btrim(unsubscribe_token) = ''" in sql
    assert "marketing_leads_token_backfill_061" in sql
    assert sql.find("INSERT INTO marketing_leads_token_backfill_061") < sql.find("UPDATE marketing_leads")
    assert "translate(" in sql and "'+/', '-_'" in sql and "'='" in sql
    assert "pgcrypto" not in sql and "gen_random_bytes" not in sql


@pytest.mark.unit
def test_061_down_undoes_only_unchanged_backfilled_rows_once():
    sql = _body_sql(DOWN)
    assert sql.strip().startswith("BEGIN;") and sql.strip().endswith("COMMIT;")
    assert "m.unsubscribe_token = b.new_token" in sql
    assert "to_regclass('public.marketing_leads_token_backfill_061') IS NULL" in sql
    assert "DELETE FROM schema_migrations WHERE filename = '061_marketing_lead_unsubscribe_token.sql';" in sql
    assert "WARNING" in DOWN.read_text(encoding="utf-8")


# ---------- migration 061 up and down on Postgres ----------

_URL = os.environ.get(
    "UPLOAD_TEST_DATABASE_URL",
    "postgresql+asyncpg://coachlenz:coachlenz@localhost:5432/coachlenz_upload_test",
).replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.mark.integration
def test_061_backfills_and_its_down_restores_on_postgres():
    import asyncpg

    async def admin(sql):
        conn = await asyncpg.connect(_URL)
        try:
            await conn.execute(sql)
        finally:
            await conn.close()

    try:
        asyncio.run(admin("SELECT 1"))
    except Exception as exc:
        if os.environ.get("CI"):
            pytest.fail(f"Postgres is required in CI ({type(exc).__name__})")
        pytest.skip(f"Postgres is not reachable ({type(exc).__name__})")

    dbname = "mig061_" + uuid.uuid4().hex[:10]
    base, _, _ = _URL.rpartition("/")
    url = f"{base}/{dbname}"
    asyncio.run(admin(f'CREATE DATABASE "{dbname}"'))
    asyncio.run(admin("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') "
                      "THEN CREATE ROLE postgres; END IF; END $$"))
    env = dict(os.environ, DATABASE_URL=url)

    def migrate():
        out = subprocess.run([sys.executable, "-m", "backend.migrate"], cwd=MIG.parents[1], env=env,
                             capture_output=True, text=True, timeout=300)
        assert out.returncode == 0, out.stderr[-2000:]
        return out.stdout

    async def scenario():
        conn = await asyncpg.connect(url)
        try:
            # Undo 061 so the rows below look like leads from before it.
            await conn.execute(DOWN.read_text(encoding="utf-8"))
            ids = {}
            for name, token in (("null", None), ("blank", ""), ("valid", VALID), ("hex", uuid.uuid4().hex)):
                ids[name] = await conn.fetchval(
                    "INSERT INTO marketing_leads(email, unsubscribe_token) VALUES ($1, $2) RETURNING id",
                    f"qa+061-{name}@coachlenz.com", token)
            before = {r["id"]: r["unsubscribe_token"] for r in await conn.fetch(
                "SELECT id, unsubscribe_token FROM marketing_leads")}

            await conn.execute(UP.read_text(encoding="utf-8"))
            after = {r["id"]: r["unsubscribe_token"] for r in await conn.fetch(
                "SELECT id, unsubscribe_token FROM marketing_leads")}
            for name in ("null", "blank"):
                tok = after[ids[name]]
                assert len(tok) == 43 and is_valid_unsubscribe_token(tok), name
            assert after[ids["null"]] != after[ids["blank"]]
            for name in ("valid", "hex"):
                assert after[ids[name]] == before[ids[name]]
            recorded = await conn.fetchval("SELECT count(*) FROM marketing_leads_token_backfill_061")
            assert recorded == 2
            assert await conn.fetchval("SELECT to_regclass('public.marketing_leads_unsubscribe_token_key')")

            # Running the up again changes nothing.
            await conn.execute(UP.read_text(encoding="utf-8"))
            again = {r["id"]: r["unsubscribe_token"] for r in await conn.fetch(
                "SELECT id, unsubscribe_token FROM marketing_leads")}
            assert again == after

            # A token changed after the backfill is kept by the down.
            await conn.execute("UPDATE marketing_leads SET unsubscribe_token = $1 WHERE id = $2",
                               "changed-after-061-0123456789abcdefghijklmn", ids["blank"])

            await conn.execute(DOWN.read_text(encoding="utf-8"))
            down = {r["id"]: r["unsubscribe_token"] for r in await conn.fetch(
                "SELECT id, unsubscribe_token FROM marketing_leads")}
            assert down[ids["null"]] is None
            assert down[ids["blank"]] == "changed-after-061-0123456789abcdefghijklmn"
            assert down[ids["valid"]] == VALID and down[ids["hex"]] == before[ids["hex"]]
            assert await conn.fetchval("SELECT to_regclass('public.marketing_leads_token_backfill_061')") is None
            assert await conn.fetchval("SELECT to_regclass('public.marketing_leads_unsubscribe_token_key')") is None
            assert await conn.fetchval(
                "SELECT count(*) FROM schema_migrations WHERE filename = '061_marketing_lead_unsubscribe_token.sql'") == 0

            # The down is safe to run twice.
            await conn.execute(DOWN.read_text(encoding="utf-8"))
        finally:
            await conn.close()

    try:
        migrate()
        asyncio.run(scenario())
        assert "applied 061_marketing_lead_unsubscribe_token.sql" in migrate()
    finally:
        asyncio.run(admin(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
