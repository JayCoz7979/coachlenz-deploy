"""Round 2 QA fixes for waitlist email (F1, F2, N1).

F1: live Resend gateway wired behind config, C1 carries the PDF link, and every
    marketing footer carries a working unsubscribe URL.
F2: /leads logs after_stored failures and stores a consent row with a null UA.
N1: the consent-pair fallback is "b".
No test talks to Resend: the live gateway runs on an httpx MockTransport.
"""
import asyncio
import json
import logging
from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest

from backend.config import settings
from backend.models.marketing_consent import EmailSuppression, MarketingConsentEvent
from backend.routers import funnel, waitlist_confirm
from backend.services import waitlist_email as mail
from backend.services.waitlist_capture import active_consent, active_pair_id

SEGMENT_IDS = {name: f"seg-{i}" for i, name in enumerate(mail.ALL_SEGMENTS)}


class _DB:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def execute(self, *_a, **_k):
        class _R:
            def scalar_one_or_none(self_inner):
                return None
        return _R()


def _lead(**kw):
    base = dict(
        id="lead-1", email="Coach@School.edu", role="parent", role_branch="general",
        school="Lincoln", sport="basketball", source="coachlenz-app-waitlist",
        lead_magnet="halftime-sheet-v1", utm_source=None, utm_medium=None,
        utm_campaign=None, utm_content=None, utm_term=None, referrer=None,
        created_at=datetime(2026, 11, 1, 12, 0, 0), confirmed_at=None,
        confirm_sent_at=None, confirm_token_hash=None, unsubscribed_at=None,
        reminder_sent_at=None, a1_sent_at=None, l1m_sent_at=None,
        unsubscribe_token="unsub-tok", has_account=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class _Recorder:
    def __init__(self, fail=False):
        self.sends = []
        self.calls = []
        self.fail = fail

    def send(self, payload):
        if self.fail:
            raise RuntimeError("gateway down")
        self.sends.append(payload)
        return {"id": "msg-1"}

    def __getattr__(self, name):
        def _call(*a, **k):
            if self.fail:
                raise RuntimeError("gateway down")
            self.calls.append((name, a))
        return _call


@pytest.fixture
def email_on(monkeypatch):
    monkeypatch.setattr(settings, "WAITLIST_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "PUBLIC_APP_URL", "https://app.coachlenz.com")
    monkeypatch.setattr(settings, "WAITLIST_HALFTIME_SHEET_URL", "")
    monkeypatch.delenv("WAITLIST_FROM", raising=False)
    yield
    mail.set_gateway(None)


# ---------- F1: footer unsubscribe and C1 PDF link ----------

@pytest.mark.unit
def test_marketing_footers_carry_a_working_unsubscribe_url(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_APP_URL", "https://staging.example.com/")
    url = "https://staging.example.com/unsubscribe?token=tok123"
    assert mail.unsubscribe_url("tok123") == url
    for text in (mail.c1_text("tok123"), mail.nurture_text("tok123"),
                 mail.launch_text("tok123"), mail.l1m_text("tok123")):
        assert url in text
        assert "one click: " + url in text


@pytest.mark.unit
def test_footer_without_a_token_never_promises_a_missing_link():
    personal = mail.standard_footer()
    assert "reply to this email or write to support@coachlenz.com with the word unsubscribe" in personal
    broadcast = mail.launch_text(broadcast=True)
    assert "{{{RESEND_UNSUBSCRIBE_URL}}}" in broadcast


@pytest.mark.unit
def test_list_unsubscribe_header_targets_the_one_click_route(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_APP_URL", "https://app.coachlenz.com")
    headers = mail._headers("tok123")
    assert headers["List-Unsubscribe"].startswith("<https://app.coachlenz.com/unsubscribe/one-click?token=tok123>")
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "waitlist/confirm?unsubscribe" not in headers["List-Unsubscribe"]


@pytest.mark.unit
def test_c1_links_the_pdf_and_defaults_to_the_existing_url(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_APP_URL", "https://app.coachlenz.com")
    monkeypatch.setattr(settings, "WAITLIST_HALFTIME_SHEET_URL", "")
    assert mail.halftime_sheet_url() == "https://app.coachlenz.com/waitlist/halftime-sheet.pdf"
    assert "Download it here: https://app.coachlenz.com/waitlist/halftime-sheet.pdf" in mail.c1_text("t")
    monkeypatch.setattr(settings, "WAITLIST_HALFTIME_SHEET_URL", "https://cdn.example.com/hs.pdf")
    assert "Download it here: https://cdn.example.com/hs.pdf" in mail.c1_text("t")


@pytest.mark.unit
def test_c1_send_has_pdf_link_footer_unsubscribe_and_header(email_on):
    gw = _Recorder()
    mail.set_gateway(gw)
    lead = _lead()
    db = _DB()
    meta = {"ip": "203.0.113.8", "ua": "CoachBrowser"}
    assert asyncio.run(mail.after_stored(db, lead, meta)) == "c0_sent"
    assert asyncio.run(mail.confirm_token(db, lead, meta)) == "confirmed"
    c1 = [p for p in gw.sends if p["kind"] == mail.TEMPLATE_C1][0]
    assert "https://app.coachlenz.com/waitlist/halftime-sheet.pdf" in c1["text"]
    assert "https://app.coachlenz.com/unsubscribe?token=unsub-tok" in c1["text"]
    assert "one-click?token=unsub-tok" in c1["headers"]["List-Unsubscribe"]
    for payload in gw.sends:
        assert "[" not in payload["text"]


@pytest.mark.unit
def test_confirm_page_download_url_matches_c1(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_APP_URL", "https://app.coachlenz.com")
    monkeypatch.setattr(settings, "WAITLIST_HALFTIME_SHEET_URL", "")
    assert waitlist_confirm.halftime_sheet_url() == "https://app.coachlenz.com/waitlist/halftime-sheet.pdf"


@pytest.mark.unit
def test_nurture_and_launch_skip_unsubscribed_leads(email_on):
    gw = _Recorder()
    mail.set_gateway(gw)
    gone = _lead(unsubscribed_at=datetime(2026, 11, 2), role_branch="coach")
    assert asyncio.run(mail.send_nurture_step(_DB(), gone)) == "unsubscribed"
    assert asyncio.run(mail.send_general_launch(_DB(), gone)) == "unsubscribed"
    assert gw.sends == []
    active = _lead(role_branch="coach")
    assert asyncio.run(mail.send_nurture_step(_DB(), active)) == "sent"
    assert "unsubscribe?token=unsub-tok" in gw.sends[0]["text"]
    assert "List-Unsubscribe" in gw.sends[0]["headers"]


# ---------- F1: gateway failures never lose the lead, consent or unsubscribe ----------

@pytest.mark.unit
def test_c0_failure_keeps_the_consent_row_and_clears_the_token(email_on, caplog):
    mail.set_gateway(_Recorder(fail=True))
    lead = _lead()
    db = _DB()
    with caplog.at_level(logging.ERROR):
        status = asyncio.run(mail.after_stored(db, lead, {"ip": "203.0.113.8", "ua": "UA"}))
    assert status == "c0_failed"
    assert [e.event_type for e in db.added if isinstance(e, MarketingConsentEvent)] == ["signup"]
    assert lead.confirm_token_hash is None and lead.confirm_sent_at is None
    assert "C0 send failed" in caplog.text
    assert "coach@school.edu" not in caplog.text.lower()


@pytest.mark.unit
def test_confirm_survives_a_sync_failure(email_on, caplog):
    lead = _lead(confirm_sent_at=datetime.utcnow())
    mail.set_gateway(_Recorder(fail=True))
    db = _DB()
    with caplog.at_level(logging.ERROR):
        status = asyncio.run(mail.confirm_token(db, lead, {"ip": "203.0.113.8", "ua": "UA"}))
    assert status == "confirmed"
    assert lead.confirmed_at is not None
    assert [e.event_type for e in db.added] == ["doi_confirmed"]
    assert lead.a1_sent_at is None
    assert "sync after confirm failed" in caplog.text


@pytest.mark.unit
def test_unsubscribe_is_recorded_locally_even_if_resend_fails(email_on, caplog):
    mail.set_gateway(_Recorder(fail=True))
    lead = _lead()
    db = _DB()
    with caplog.at_level(logging.ERROR):
        assert asyncio.run(mail.unsubscribe_lead(db, lead)) == "unsubscribed"
    assert lead.unsubscribed_at is not None
    assert any(isinstance(o, EmailSuppression) for o in db.added)
    assert "unsubscribe failed" in caplog.text


# ---------- F1: the live gateway ----------

def _live(monkeypatch, handler, configured=True):
    monkeypatch.setattr(settings, "WAITLIST_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_not_real" if configured else "")
    monkeypatch.setattr(settings, "WAITLIST_RESEND_TOPIC_ID", "topic-1" if configured else "")
    monkeypatch.setattr(settings, "WAITLIST_RESEND_SEGMENT_IDS", json.dumps(SEGMENT_IDS) if configured else "")
    return mail.ResendGateway(transport=httpx.MockTransport(handler))


@pytest.mark.unit
def test_live_gateway_is_a_no_op_with_email_off(monkeypatch):
    seen = []
    gw = _live(monkeypatch, lambda r: seen.append(r) or httpx.Response(200, json={}))
    monkeypatch.setattr(settings, "WAITLIST_EMAIL_ENABLED", False)
    gw.upsert_contact("a@b.co", {})
    gw.add_to_segment("a@b.co", mail.ALL_CONFIRMED)
    gw.send_event(mail.CONFIRMED_EVENT, "a@b.co", {})
    gw.unsubscribe_contact("a@b.co", mail.COACHLENZ_TOPIC)
    assert gw.send({"text": "x"}) == {}
    assert seen == []


@pytest.mark.unit
def test_live_gateway_refuses_everything_until_configured(monkeypatch):
    seen = []
    gw = _live(monkeypatch, lambda r: seen.append(r) or httpx.Response(200, json={}), configured=False)
    missing = mail.resend_config_missing()
    assert missing[0] == "RESEND_API_KEY" and missing[1] == "WAITLIST_RESEND_TOPIC_ID"
    assert missing[2].startswith("WAITLIST_RESEND_SEGMENT_IDS (")
    for call in (
        lambda: gw.send({"text": "hello"}),
        lambda: gw.upsert_contact("a@b.co", {}),
        lambda: gw.add_to_segment("a@b.co", mail.ALL_CONFIRMED),
        lambda: gw.send_event(mail.CONFIRMED_EVENT, "a@b.co", {}),
        lambda: gw.unsubscribe_contact("a@b.co", mail.COACHLENZ_TOPIC),
    ):
        with pytest.raises(RuntimeError, match="not configured"):
            call()
    assert seen == []


@pytest.mark.unit
def test_live_gateway_calls_the_resend_contact_segment_event_and_topic_apis(monkeypatch):
    seen = []

    def handler(request):
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, body, request.headers.get("authorization")))
        return httpx.Response(202 if request.url.path == "/events/send" else 200, json={"id": "x"})

    gw = _live(monkeypatch, handler)
    gw.upsert_contact("Coach@School.edu", {"role": "head_coach", "confirmed_at": datetime(2026, 11, 3), "has_account": False, "school": None})
    gw.add_to_segment("coach@school.edu", mail.ALL_CONFIRMED)
    gw.remove_from_segment("coach@school.edu", mail.L2_SEGMENT)
    gw.send_event(mail.CONFIRMED_EVENT, "coach@school.edu", {"role_branch": "coach"})
    gw.unsubscribe_contact("coach@school.edu", mail.COACHLENZ_TOPIC)
    methods = [(m, p) for m, p, _b, _a in seen]
    assert methods == [
        ("POST", "/contacts"),
        ("POST", f"/contacts/coach@school.edu/segments/{SEGMENT_IDS[mail.ALL_CONFIRMED]}"),
        ("DELETE", f"/contacts/coach@school.edu/segments/{SEGMENT_IDS[mail.L2_SEGMENT]}"),
        ("POST", "/events/send"),
        ("PATCH", "/contacts/coach@school.edu/topics"),
    ]
    create = seen[0][2]
    assert create["email"] == "coach@school.edu"
    assert create["topics"] == [{"id": "topic-1", "subscription": "opt_in"}]
    assert create["properties"] == {"role": "head_coach", "confirmed_at": "2026-11-03T00:00:00", "has_account": "false"}
    assert seen[3][2] == {"event": mail.CONFIRMED_EVENT, "email": "coach@school.edu", "payload": {"role_branch": "coach"}}
    assert seen[4][2] == {"topics": [{"id": "topic-1", "subscription": "opt_out"}]}
    assert all(a == "Bearer re_test_not_real" for *_x, a in seen)


@pytest.mark.unit
def test_live_upsert_updates_an_existing_contact(monkeypatch):
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        if request.method == "POST" and request.url.path == "/contacts":
            return httpx.Response(409, json={"message": "exists"})
        return httpx.Response(200, json={})

    gw = _live(monkeypatch, handler)
    gw.upsert_contact("coach@school.edu", {"role": "head_coach"})
    assert seen == [
        ("POST", "/contacts"),
        ("PATCH", "/contacts/coach@school.edu"),
        ("PATCH", "/contacts/coach@school.edu/topics"),
    ]


@pytest.mark.unit
def test_live_gateway_guards_and_error_text_never_includes_the_address(monkeypatch):
    gw = _live(monkeypatch, lambda r: httpx.Response(500, json={"message": "coach@school.edu broke"}))
    with pytest.raises(RuntimeError, match='named "General"'):
        gw.add_to_segment("coach@school.edu", mail.FORBIDDEN_SEGMENT)
    with pytest.raises(RuntimeError, match="No Resend segment id"):
        gw.add_to_segment("coach@school.edu", "Some Other Segment")
    with pytest.raises(RuntimeError, match="not CoachLenz updates"):
        gw.unsubscribe_contact("coach@school.edu", "Other list")
    with pytest.raises(RuntimeError) as exc:
        gw.send_event(mail.CONFIRMED_EVENT, "coach@school.edu", {})
    assert "HTTP 500" in str(exc.value)
    assert "coach@school.edu" not in str(exc.value)


@pytest.mark.unit
def test_live_payloads_never_carry_ip_or_user_agent(monkeypatch):
    seen = []
    gw = _live(monkeypatch, lambda r: seen.append(json.loads(r.content)) or httpx.Response(200, json={}))
    gw.upsert_contact("a@b.co", {"role": "x", "ip_address": "203.0.113.9", "user_agent": "UA"})
    gw.send_event(mail.CONFIRMED_EVENT, "a@b.co", {"ip": "203.0.113.9", "ua": "UA"})
    blob = json.dumps(seen)
    assert "203.0.113.9" not in blob and "UA\"" not in blob


# ---------- F2 ----------

@pytest.mark.unit
def test_empty_user_agent_still_writes_the_consent_row_with_null_ua(monkeypatch):
    monkeypatch.setattr(settings, "WAITLIST_EMAIL_ENABLED", False)
    db = _DB()
    assert asyncio.run(mail.after_stored(db, _lead(), {"ip": "203.0.113.8", "ua": ""})) == "stored_no_email"
    events = [o for o in db.added if isinstance(o, MarketingConsentEvent)]
    assert len(events) == 1
    assert events[0].ip_address == "203.0.113.8"
    assert events[0].user_agent is None


@pytest.mark.unit
def test_missing_ip_is_still_refused():
    with pytest.raises(ValueError, match="ip_address"):
        mail._event(_lead(), "signup", {"ip": "", "ua": "UA"})


class _LeadDB(_DB):
    async def execute(self, *_a, **_k):
        class _R:
            def scalar_one_or_none(self_inner):
                return None
        return _R()


@pytest.mark.unit
def test_leads_logs_an_after_stored_failure_and_still_returns_ok(monkeypatch, caplog):
    async def _boom(*_a, **_k):
        raise RuntimeError("consent write failed")

    monkeypatch.setattr(mail, "after_stored", _boom)
    body = funnel.LeadIn(email="coach@school.edu", source="coachlenz-app-waitlist",
                         first_name="Ada", role="head_coach")
    req = SimpleNamespace(client=SimpleNamespace(host="203.0.113.8"), headers={})
    db = _LeadDB()
    fn = getattr(funnel.capture_lead, "__wrapped__", funnel.capture_lead)
    with caplog.at_level(logging.ERROR, logger="backend.routers.funnel"):
        out = asyncio.run(fn(body, req, db))
    assert out == {"ok": True}
    assert "after_stored failed" in caplog.text
    assert "consent write failed" in caplog.text
    assert "coach@school.edu" not in caplog.text
    assert db.rollbacks == 1


# ---------- N1 ----------

@pytest.mark.unit
@pytest.mark.parametrize("raw", ["", "   ", None])
def test_empty_consent_pair_falls_back_to_b(monkeypatch, raw):
    monkeypatch.setattr(settings, "WAITLIST_CONSENT_PAIR", raw)
    assert active_pair_id() == "b"
    assert active_consent()["button"] == "Send me the Halftime Sheet"
