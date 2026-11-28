"""Free printable Halftime Sheet PDF: double opt-in lead form. No DB, no DNS, no email.

Drives the REAL router over HTTP (slim app + the real slowapi limiter) with an in-memory
LeadStore, a fake MX resolver, and the two outbound sends captured instead of sent.

Covers the asks in #299 (Jason, Nov 28): pending -> confirmed flow, expired token,
reused token, invalid email rejected, PDF not deliverable before confirm, tokens hashed
at rest, resend for expired/used links, rate limits on submit + resend, honeypot,
optional phone (never texted), and the staging outbound allowlist.
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.config import settings
from backend.ratelimit import limiter
from backend.routers import halftime_leads as router_mod
from backend.services import email_service
from backend.services import halftime_leads as svc
from backend.services.halftime_pdf import PDF_FILENAME, halftime_sheet_pdf

pytestmark = pytest.mark.unit


class MemStore:
    """In-memory LeadStore. Rows are plain objects so the flow mutates them like ORM rows."""

    def __init__(self):
        self.rows = []
        self.commits = 0

    async def get_by_email(self, email):
        return next((r for r in self.rows if r.email.lower() == email.lower()), None)

    async def get_by_token_hash(self, h):
        return next((r for r in self.rows if r.token_hash == h), None)

    async def get_by_id(self, lead_id):
        return next((r for r in self.rows if str(r.id) == str(lead_id)), None)

    async def add(self, lead):
        self.rows.append(lead)

    async def claim_token(self, lead, h, now):
        if lead.token_hash == h and lead.token_used_at is None and lead.token_expires_at > now:
            lead.token_used_at = now
            return True
        return False

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


class Outbox:
    def __init__(self):
        self.confirms = []   # (to, name, url)
        self.pdfs = []       # (to, name)
        self.unsub_tokens = []
        self.fail_confirm = False
        self.fail_pdf = False

    async def confirm(self, to, name, url, unsub_token):
        if self.fail_confirm:
            raise RuntimeError("provider down")
        self.confirms.append((to, name, url))
        self.unsub_tokens.append(unsub_token)
        return True

    async def pdf(self, to, name, unsub_token):
        if self.fail_pdf:
            raise RuntimeError("provider down")
        self.pdfs.append((to, name))
        self.unsub_tokens.append(unsub_token)
        return True


def _new_lead_plain(*, name, email, phone, ip, now):
    return SimpleNamespace(
        id=uuid.uuid4(), name=name, email=email, phone=phone, source=svc.SOURCE, status="pending",
        consent_text=svc.CONSENT_TEXT, consented_at=now, submit_ip=ip, token_hash=None,
        token_expires_at=None, token_used_at=None, confirmation_sent_at=None,
        confirmation_send_count=0, confirmed_at=None, confirmed_ip=None, pdf_sent_at=None,
        unsubscribed_at=None, created_at=now, updated_at=now,
    )


async def _mx_ok(domain):
    return domain not in {"no-mail.example", "nxdomain.example"}


@pytest.fixture
def env(monkeypatch):
    store, out = MemStore(), Outbox()
    monkeypatch.setattr(svc, "_send_confirmation_email", out.confirm)
    monkeypatch.setattr(svc, "_send_pdf_email", out.pdf)
    monkeypatch.setattr(svc, "_new_lead", _new_lead_plain)
    monkeypatch.setattr(svc, "domain_accepts_mail", _mx_ok)
    limiter.reset()
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(router_mod.router)
    app.dependency_overrides[router_mod.get_lead_store] = lambda: store
    client = TestClient(app)
    yield SimpleNamespace(store=store, out=out, client=client)
    limiter.reset()


GOOD = {"name": "Test Coach", "email": "qa.coach@example.com", "consent": True}


def _token_from(url: str) -> str:
    return parse_qs(urlparse(url).query)["token"][0]


def _submit(env, **over):
    return env.client.post("/leads/halftime-sheet", json={**GOOD, **over})


# ── 1. pending -> confirmed, and the PDF only after confirm ─────────────────────
def test_submit_stores_pending_and_sends_only_a_confirmation_link(env):
    r = _submit(env, phone="(555) 010-0000")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"
    [lead] = env.store.rows
    assert lead.status == "pending" and lead.source == "halftime_pdf"
    assert lead.email == "qa.coach@example.com" and lead.phone == "(555) 010-0000"
    assert lead.consent_text == svc.CONSENT_TEXT and lead.consented_at is not None
    assert len(env.out.confirms) == 1
    assert env.out.pdfs == []                       # PDF NOT sent on submit
    assert b"%PDF" not in r.content                  # no file in the response
    assert r.headers["content-type"].startswith("application/json")


def test_confirm_marks_confirmed_with_timestamp_and_ip_then_emails_pdf(env):
    _submit(env)
    token = _token_from(env.out.confirms[0][2])
    assert env.out.pdfs == []
    r = env.client.post("/leads/halftime-sheet/confirm", json={"token": token})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "confirmed"
    [lead] = env.store.rows
    assert lead.status == "confirmed"
    assert lead.confirmed_at is not None
    assert lead.confirmed_ip == "testclient"
    assert lead.token_used_at is not None
    assert env.out.pdfs == [("qa.coach@example.com", "Test Coach")]
    assert lead.pdf_sent_at is not None


def test_confirm_link_points_at_the_configured_frontend(env, monkeypatch):
    monkeypatch.setattr(settings, "LEAD_CONFIRM_BASE_URL", "https://staging.example.test/")
    _submit(env)
    url = env.out.confirms[0][2]
    assert url.startswith("https://staging.example.test/live-tracker/halftime-sheet/confirm?token=")


def test_no_route_serves_the_pdf_before_or_without_confirmation(env):
    """The PDF never leaves the server except as an attachment after confirm."""
    _submit(env)
    paths = {getattr(r, "path", "") for r in env.client.app.routes}
    assert not any("pdf" in p or "download" in p for p in paths), paths
    for p in ("/leads/halftime-sheet/pdf", "/leads/halftime-sheet/download"):
        assert env.client.get(p).status_code in (404, 405)
    # A bogus token never yields the PDF.
    r = env.client.post("/leads/halftime-sheet/confirm", json={"token": "not-a-real-token"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "token_invalid"
    assert env.out.pdfs == []
    assert env.store.rows[0].status == "pending"


def test_pending_lead_resend_still_sends_no_pdf(env):
    _submit(env)
    env.store.rows[0].confirmation_sent_at -= timedelta(minutes=5)
    r = env.client.post("/leads/halftime-sheet/resend", json={"email": GOOD["email"]})
    assert r.status_code == 200
    assert len(env.out.confirms) == 2 and env.out.pdfs == []


# ── 2. tokens: hashed at rest, single use, 24h expiry ──────────────────────────
def test_token_is_hashed_at_rest_never_stored_raw(env):
    _submit(env)
    token = _token_from(env.out.confirms[0][2])
    lead = env.store.rows[0]
    assert lead.token_hash and lead.token_hash != token and token not in lead.token_hash
    assert lead.token_hash == svc.hash_token(token)
    assert len(lead.token_hash) == 64           # hex HMAC-SHA256
    assert all(token not in str(v) for v in vars(lead).values())


def test_token_expires_after_24_hours(env):
    _submit(env)
    lead = env.store.rows[0]
    sent = lead.confirmation_sent_at
    assert lead.token_expires_at - sent == timedelta(hours=24)


def test_expired_token_is_rejected_and_offers_resend(env):
    _submit(env)
    token = _token_from(env.out.confirms[0][2])
    lead = env.store.rows[0]
    lead.token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    r = env.client.post("/leads/halftime-sheet/confirm", json={"token": token})
    assert r.status_code == 410
    d = r.json()["detail"]
    assert d["code"] == "token_expired" and d["resend_available"] is True
    assert lead.status == "pending" and env.out.pdfs == []
    # Resend by the expired token issues a fresh link that works.
    lead.confirmation_sent_at -= timedelta(minutes=5)
    r = env.client.post("/leads/halftime-sheet/resend", json={"token": token})
    assert r.status_code == 200 and len(env.out.confirms) == 2
    new_token = _token_from(env.out.confirms[1][2])
    assert new_token != token
    assert env.client.post("/leads/halftime-sheet/confirm", json={"token": new_token}).status_code == 200
    assert lead.status == "confirmed" and len(env.out.pdfs) == 1


def test_reused_token_is_rejected_and_does_not_resend_the_pdf(env):
    _submit(env)
    token = _token_from(env.out.confirms[0][2])
    assert env.client.post("/leads/halftime-sheet/confirm", json={"token": token}).status_code == 200
    first_confirmed_at = env.store.rows[0].confirmed_at
    r = env.client.post("/leads/halftime-sheet/confirm", json={"token": token})
    assert r.status_code == 410
    d = r.json()["detail"]
    assert d["code"] == "token_used" and d["resend_available"] is True and d["already_confirmed"] is True
    assert len(env.out.pdfs) == 1                       # still exactly one PDF
    assert env.store.rows[0].confirmed_at == first_confirmed_at


def test_new_link_invalidates_the_previous_one(env):
    _submit(env)
    old = _token_from(env.out.confirms[0][2])
    env.store.rows[0].confirmation_sent_at -= timedelta(minutes=5)
    env.client.post("/leads/halftime-sheet/resend", json={"email": GOOD["email"]})
    r = env.client.post("/leads/halftime-sheet/confirm", json={"token": old})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "token_invalid"
    assert env.out.pdfs == []


def test_concurrent_double_click_sends_one_pdf(env, monkeypatch):
    """claim_token is the atomic gate: if another click claimed it first, no second PDF."""
    _submit(env)
    token = _token_from(env.out.confirms[0][2])

    async def lost_race(lead, h, now):
        return False
    monkeypatch.setattr(env.store, "claim_token", lost_race)
    r = env.client.post("/leads/halftime-sheet/confirm", json={"token": token})
    assert r.status_code == 410 and r.json()["detail"]["code"] == "token_used"
    assert env.out.pdfs == [] and env.store.rows[0].status == "pending"


# ── 3. validation ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("email,code", [
    ("not-an-email", "invalid_email"),
    ("coach@", "invalid_email"),
    ("", "invalid_email"),
    ("coach@mailinator.com", "disposable_email"),
    ("coach@nxdomain.example", "email_domain_invalid"),
])
def test_invalid_email_is_rejected_and_nothing_is_stored_or_sent(env, email, code):
    r = _submit(env, email=email)
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == code
    assert env.store.rows == [] and env.out.confirms == [] and env.out.pdfs == []


def test_name_and_consent_are_required_phone_is_optional(env):
    assert _submit(env, name="").json()["detail"]["code"] == "invalid_name"
    assert _submit(env, name="http://spam.example").json()["detail"]["code"] == "invalid_name"
    assert _submit(env, consent=False).json()["detail"]["code"] == "consent_required"
    assert _submit(env, phone="abc").json()["detail"]["code"] == "invalid_phone"
    assert env.store.rows == []
    r = _submit(env)       # no phone at all
    assert r.status_code == 200 and env.store.rows[0].phone is None


def test_email_is_normalised_and_deduplicated(env):
    _submit(env, email="QA.Coach@Example.com")
    env.store.rows[0].confirmation_sent_at -= timedelta(minutes=5)
    _submit(env, email="qa.coach@example.com")
    assert len(env.store.rows) == 1 and env.store.rows[0].email == "qa.coach@example.com"


async def test_mx_check_uses_dns_and_rejects_a_dead_domain(monkeypatch):
    async def resolver(domain):
        return domain == "example.com"
    assert await svc.validate_email_address("a@example.com", resolver) == "a@example.com"
    with pytest.raises(svc.LeadError) as e:
        await svc.validate_email_address("a@no-mail.example", resolver)
    assert e.value.code == "email_domain_invalid"


# ── 4. abuse controls ──────────────────────────────────────────────────────────
def test_honeypot_returns_success_but_stores_and_sends_nothing(env):
    r = _submit(env, company="Acme Bots LLC")
    assert r.status_code == 200 and r.json()["status"] == "pending"
    assert env.store.rows == [] and env.out.confirms == []


def test_submit_is_rate_limited_per_ip(env):
    codes = [_submit(env, email=f"qa{i}@example.com").status_code for i in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


def test_resend_is_rate_limited_per_ip(env):
    codes = [env.client.post("/leads/halftime-sheet/resend", json={"email": f"x{i}@example.com"}).status_code
             for i in range(4)]
    assert codes[:3] == [200] * 3 and codes[3] == 429


def test_per_address_cooldown_blocks_mail_bombing_but_answers_the_same(env):
    _submit(env)
    r = env.client.post("/leads/halftime-sheet/resend", json={"email": GOOD["email"]})
    assert r.status_code == 200
    assert len(env.out.confirms) == 1     # inside the 60s cooldown: nothing new sent


def test_resend_for_unknown_address_gives_the_generic_answer(env):
    r = env.client.post("/leads/halftime-sheet/resend", json={"email": "nobody@example.com"})
    assert r.status_code == 200 and env.out.confirms == []


# ── 5. honest failures ─────────────────────────────────────────────────────────
def test_confirmation_send_failure_is_502_and_retry_is_not_blocked(env):
    env.out.fail_confirm = True
    r = _submit(env)
    assert r.status_code == 502 and r.json()["detail"]["code"] == "email_send_failed"
    lead = env.store.rows[0]
    assert lead.status == "pending" and lead.token_hash is None and lead.confirmation_sent_at is None
    env.out.fail_confirm = False
    r = _submit(env)                       # immediate retry works (no cooldown was set)
    assert r.status_code == 200 and len(env.out.confirms) == 1


def test_pdf_send_failure_keeps_confirmation_and_offers_a_new_link(env):
    _submit(env)
    token = _token_from(env.out.confirms[0][2])
    env.out.fail_pdf = True
    r = env.client.post("/leads/halftime-sheet/confirm", json={"token": token})
    assert r.status_code == 502
    d = r.json()["detail"]
    assert d["code"] == "pdf_send_failed" and d["already_confirmed"] is True and d["resend_available"] is True
    lead = env.store.rows[0]
    assert lead.status == "confirmed" and lead.pdf_sent_at is None
    # A fresh link re-delivers the PDF to the confirmed address.
    env.out.fail_pdf = False
    lead.confirmation_sent_at -= timedelta(minutes=5)
    env.client.post("/leads/halftime-sheet/resend", json={"token": token})
    t2 = _token_from(env.out.confirms[-1][2])
    assert env.client.post("/leads/halftime-sheet/confirm", json={"token": t2}).status_code == 200
    assert len(env.out.pdfs) == 1 and lead.pdf_sent_at is not None


# ── 6. outbound safety + no SMS ────────────────────────────────────────────────
def test_staging_outbound_is_allowlist_only_by_default(monkeypatch):
    monkeypatch.setattr(settings, "LEAD_EMAIL_LIVE_SEND", False)
    monkeypatch.setattr(settings, "LEAD_EMAIL_ALLOWLIST", "qa1@example.com, @qa.example.org")
    assert email_service.lead_email_allowed("qa1@example.com")
    assert email_service.lead_email_allowed("QA1@Example.com")
    assert email_service.lead_email_allowed("anyone@qa.example.org")
    assert not email_service.lead_email_allowed("real.coach@gmail.com")
    assert not email_service.lead_email_allowed("x@sub.qa.example.org.evil.com")
    monkeypatch.setattr(settings, "LEAD_EMAIL_ALLOWLIST", "")
    assert not email_service.lead_email_allowed("qa1@example.com")
    monkeypatch.setattr(settings, "LEAD_EMAIL_LIVE_SEND", True)
    assert email_service.lead_email_allowed("real.coach@gmail.com")


@pytest.fixture
def compliance(monkeypatch):
    monkeypatch.setattr(settings, "COMPANY_POSTAL_ADDRESS", "123 Test St, Testville, TX 00000")
    monkeypatch.setattr(settings, "PUBLIC_API_URL", "https://api.example.test/")
    monkeypatch.setattr(settings, "LEAD_CONFIRM_BASE_URL", "https://app.example.test")


UNSUB = "lead-id.sig"


async def test_suppressed_recipient_is_never_handed_to_the_provider(monkeypatch, compliance):
    sent = []
    monkeypatch.setattr(email_service.resend.Emails, "send", lambda payload: sent.append(payload))
    monkeypatch.setattr(settings, "LEAD_EMAIL_LIVE_SEND", False)
    monkeypatch.setattr(settings, "LEAD_EMAIL_ALLOWLIST", "qa1@example.com")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_placeholder")
    assert await email_service.send_halftime_confirm_email("real.coach@gmail.com", "Coach", "https://x/c?token=t", UNSUB) is False
    assert await email_service.send_halftime_pdf_email("real.coach@gmail.com", "Coach", b"%PDF", "a.pdf", UNSUB) is False
    assert sent == []
    assert await email_service.send_halftime_pdf_email("qa1@example.com", "Test Coach", halftime_sheet_pdf(), PDF_FILENAME, UNSUB) is True
    [payload] = sent
    assert payload["to"] == "qa1@example.com"
    [att] = payload["attachments"]
    assert att["filename"] == PDF_FILENAME and bytes(att["content"]).startswith(b"%PDF-")


async def test_missing_email_provider_raises_instead_of_pretending(monkeypatch, compliance):
    monkeypatch.setattr(settings, "LEAD_EMAIL_LIVE_SEND", True)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    with pytest.raises(RuntimeError):
        await email_service.send_halftime_confirm_email("qa1@example.com", "Coach", "https://x", UNSUB)


def test_no_sms_and_no_invented_claims_in_lead_copy():
    import inspect
    src = (inspect.getsource(svc) + inspect.getsource(router_mod)
           + inspect.getsource(email_service.send_halftime_confirm_email)
           + inspect.getsource(email_service.send_halftime_pdf_email)).lower()
    assert "twilio" not in src
    for banned in ("free forever", "no card", "$0"):
        assert banned not in src
    assert "never texted" in svc.CONSENT_TEXT.lower()


def test_pdf_is_a_real_two_page_pdf_with_the_halftime_sheet():
    pdf = halftime_sheet_pdf()
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    assert b"/Count 2" in pdf
    assert b"CoachLenz Halftime Sheet" in pdf and b"HALFTIME SHEET" in pdf
    assert b"Football / Flag Football" in pdf and b"Basketball" in pdf
    assert b"$" not in pdf.split(b"stream")[1]   # no prices on the sheet


# ── 7. Stage 2 QA M2: one-click unsubscribe, List-Unsubscribe, postal address ───
def _confirmed_lead(env):
    _submit(env)
    t = _token_from(env.out.confirms[-1][2])
    assert env.client.post("/leads/halftime-sheet/confirm", json={"token": t}).status_code == 200
    return env.store.rows[0]


def test_every_lead_email_carries_a_signed_unsubscribe_token_for_that_lead(env):
    lead = _confirmed_lead(env)
    assert len(env.out.unsub_tokens) == 2                        # confirmation + PDF
    for tok in env.out.unsub_tokens:
        assert svc.verify_unsubscribe_token(tok) == str(lead.id)


def test_one_click_unsubscribe_from_the_list_unsubscribe_header(env):
    lead = _confirmed_lead(env)
    tok = env.out.unsub_tokens[-1]
    # RFC 8058: the mail client POSTs this exact form body to the header URL.
    r = env.client.post(f"/leads/halftime-sheet/unsubscribe?token={tok}",
                        content="List-Unsubscribe=One-Click",
                        headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "unsubscribed"
    assert lead.status == "unsubscribed" and lead.unsubscribed_at is not None
    # Idempotent: a second click gets the same answer.
    r = env.client.post("/leads/halftime-sheet/unsubscribe", json={"token": tok})
    assert r.status_code == 200 and lead.status == "unsubscribed"


def test_unsubscribed_lead_gets_no_more_email_from_resend(env):
    lead = _confirmed_lead(env)
    sent_before = (len(env.out.confirms), len(env.out.pdfs))
    env.client.post("/leads/halftime-sheet/unsubscribe", json={"token": env.out.unsub_tokens[-1]})
    lead.confirmation_sent_at = None                             # cooldown is not what stops it
    r = env.client.post("/leads/halftime-sheet/resend", json={"email": lead.email})
    assert r.status_code == 200                                  # same generic answer
    assert (len(env.out.confirms), len(env.out.pdfs)) == sent_before


def test_unsubscribe_kills_an_outstanding_confirmation_link(env):
    _submit(env)
    lead = env.store.rows[0]
    t = _token_from(env.out.confirms[-1][2])
    env.client.post("/leads/halftime-sheet/unsubscribe", json={"token": env.out.unsub_tokens[-1]})
    assert lead.token_hash is None
    r = env.client.post("/leads/halftime-sheet/confirm", json={"token": t})
    assert r.status_code == 400 and env.out.pdfs == []


def test_resubmitting_the_form_is_a_new_explicit_opt_in(env):
    lead = _confirmed_lead(env)
    env.client.post("/leads/halftime-sheet/unsubscribe", json={"token": env.out.unsub_tokens[-1]})
    lead.confirmation_sent_at = None
    assert _submit(env).status_code == 200
    assert lead.status == "pending" and len(env.out.confirms) == 2


@pytest.mark.parametrize("tok", ["", "nonsense", "abc.def", None])
def test_forged_or_garbled_unsubscribe_token_is_refused(env, tok):
    lead = _confirmed_lead(env)
    real = env.out.unsub_tokens[-1]
    forged = real[:-1] + ("0" if real[-1] != "0" else "1")
    for bad in ([tok] if tok is not None else [forged]):
        r = env.client.post("/leads/halftime-sheet/unsubscribe", json={"token": bad})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "token_invalid"
    assert lead.status == "confirmed"


def test_unsubscribe_token_for_one_lead_cannot_be_moved_to_another():
    tok = svc.unsubscribe_token("11111111-1111-1111-1111-111111111111")
    _lid, sig = tok.rsplit(".", 1)
    assert svc.verify_unsubscribe_token(f"22222222-2222-2222-2222-222222222222.{sig}") is None


def test_unsubscribe_is_rate_limited_per_ip(env):
    codes = [env.client.post("/leads/halftime-sheet/unsubscribe", json={"token": "x.y"}).status_code
             for _ in range(61)]
    assert codes[-1] == 429


async def test_lead_email_has_list_unsubscribe_headers_footer_link_and_postal_address(monkeypatch, compliance):
    sent = []
    monkeypatch.setattr(email_service.resend.Emails, "send", lambda payload: sent.append(payload))
    monkeypatch.setattr(settings, "LEAD_EMAIL_LIVE_SEND", False)
    monkeypatch.setattr(settings, "LEAD_EMAIL_ALLOWLIST", "qa1@example.com")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_placeholder")
    tok = svc.unsubscribe_token("11111111-1111-1111-1111-111111111111")
    assert await email_service.send_halftime_pdf_email("qa1@example.com", "Test Coach", b"%PDF-1.4", "a.pdf", tok)
    assert await email_service.send_halftime_confirm_email("qa1@example.com", "Test Coach", "https://x/c?token=t", tok)
    for payload in sent:
        h = payload["headers"]
        assert h["List-Unsubscribe"] == f"<https://api.example.test/leads/halftime-sheet/unsubscribe?token={tok}>"
        assert h["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert f"https://app.example.test/live-tracker/halftime-sheet/unsubscribe?token={tok}" in payload["html"]
        assert "Unsubscribe" in payload["html"]
        assert "123 Test St, Testville, TX 00000" in payload["html"]


@pytest.mark.parametrize("missing", ["COMPANY_POSTAL_ADDRESS", "PUBLIC_API_URL"])
async def test_lead_email_fails_closed_without_postal_address_or_api_url(monkeypatch, compliance, missing):
    sent = []
    monkeypatch.setattr(email_service.resend.Emails, "send", lambda payload: sent.append(payload))
    monkeypatch.setattr(settings, "LEAD_EMAIL_LIVE_SEND", True)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_placeholder")
    monkeypatch.setattr(settings, missing, "  ")
    tok = svc.unsubscribe_token("11111111-1111-1111-1111-111111111111")
    with pytest.raises(email_service.LeadEmailNotConfigured) as e1:
        await email_service.send_halftime_pdf_email("qa1@example.com", "Coach", b"%PDF", "a.pdf", tok)
    with pytest.raises(email_service.LeadEmailNotConfigured):
        await email_service.send_halftime_confirm_email("qa1@example.com", "Coach", "https://x", tok)
    assert missing in str(e1.value)
    assert sent == []


def test_confirm_without_postal_address_sends_no_pdf_and_says_so(env, monkeypatch, compliance):
    """End to end through the real send function: no address -> nothing reaches the
    provider, the coach gets an honest 502, and the confirmation itself is kept."""
    sent = []
    monkeypatch.setattr(email_service.resend.Emails, "send", lambda payload: sent.append(payload))
    monkeypatch.setattr(settings, "LEAD_EMAIL_LIVE_SEND", True)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_placeholder")
    monkeypatch.setattr(svc, "_send_pdf_email", _real_send_pdf)
    monkeypatch.setattr(settings, "COMPANY_POSTAL_ADDRESS", "")
    _submit(env)
    t = _token_from(env.out.confirms[-1][2])
    r = env.client.post("/leads/halftime-sheet/confirm", json={"token": t})
    assert r.status_code == 502 and r.json()["detail"]["code"] == "pdf_send_failed"
    assert env.store.rows[0].status == "confirmed" and env.store.rows[0].pdf_sent_at is None
    assert sent == []


async def _real_send_pdf(to, name, unsub_token):
    from backend.services.halftime_pdf import PDF_FILENAME, halftime_sheet_pdf
    return await email_service.send_halftime_pdf_email(to, name, halftime_sheet_pdf(), PDF_FILENAME, unsub_token)


def test_consent_promise_of_unsubscribe_is_backed_by_a_route():
    assert "unsubscribe" in svc.CONSENT_TEXT.lower()
    paths = {r.path for r in router_mod.router.routes}
    assert "/leads/halftime-sheet/unsubscribe" in paths
