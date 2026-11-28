"""
Free printable Halftime Sheet PDF lead form (/live-tracker). No DB, no network, no DNS.

Covers:
  * email validation: format, disposable domains (and subdomains), MX / implicit-MX /
    NXDOMAIN / null-MX, and the DNS-outage policy (accept + log, never drop a lead).
  * POST /leads/halftime-pdf over real HTTP (slim app, real router, fake DB): name +
    valid email required, phone optional (blank OK, junk rejected), consent required,
    honeypot stores nothing and returns no link, repeat email reuses one row, stored
    with source='halftime_pdf' and a timestamp, rate limit returns 429.
  * GET download: valid token returns a real 2-page PDF; unknown token 404.
  * copy rules: no SMS, no "free forever", only the $7 one-time price.
"""
import asyncio
import uuid
from types import SimpleNamespace

import dns.exception
import dns.resolver
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.models.base import get_db
from backend.ratelimit import limiter
from backend.routers import lead_magnet
from backend.services import email_check
from backend.services.halftime_pdf import halftime_sheet_pdf, FOOTER_OFFER

pytestmark = pytest.mark.unit


# ── fake DNS ────────────────────────────────────────────────────────────────
def _mx(*hosts):
    return [SimpleNamespace(exchange=h) for h in hosts]


def _dns(table):
    """table: {(domain, rdtype): answer-list | exception class}. Missing -> NoAnswer."""
    async def _resolve(domain, rdtype):
        v = table.get((domain, rdtype), dns.resolver.NoAnswer)
        if isinstance(v, type) and issubclass(v, BaseException):
            raise v()
        return v
    return _resolve


GOOD_DNS = {("coachmail.com", "MX"): _mx("mx1.coachmail.com.")}


@pytest.fixture
def good_dns(monkeypatch):
    monkeypatch.setattr(email_check, "_resolve", _dns(GOOD_DNS))


def _validate(raw):
    return asyncio.run(email_check.validate_lead_email(raw))


# ── email validation ────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["", "   ", "not-an-email", "coach@", "@coachmail.com",
                                 "coach@@coachmail.com", "coach@coachmail", "a b@coachmail.com",
                                 "x" * 250 + "@coachmail.com"])
def test_format_rejected(bad, good_dns):
    with pytest.raises(email_check.EmailRejected):
        _validate(bad)


def test_valid_email_is_normalized(good_dns):
    assert _validate("  Coach.Smith@CoachMail.com ") == "coach.smith@coachmail.com"


@pytest.mark.parametrize("addr", ["x@mailinator.com", "x@YOPMAIL.com", "x@inbox.guerrillamail.com",
                                  "x@10minutemail.com"])
def test_disposable_domains_rejected_without_dns(addr, monkeypatch):
    async def _boom(*_a, **_k):
        raise AssertionError("disposable check must run before any DNS lookup")
    monkeypatch.setattr(email_check, "_resolve", _boom)
    with pytest.raises(email_check.EmailRejected, match="disposable"):
        _validate(addr)


def test_is_disposable_does_not_match_lookalikes():
    assert email_check.is_disposable("mailinator.com")
    assert email_check.is_disposable("a.b.mailinator.com")
    assert not email_check.is_disposable("notmailinator.com")
    assert not email_check.is_disposable("gmail.com")


def test_domain_that_does_not_exist_is_rejected(monkeypatch):
    monkeypatch.setattr(email_check, "_resolve", _dns({("nope-xyz.com", "MX"): dns.resolver.NXDOMAIN}))
    with pytest.raises(email_check.EmailRejected, match="can't receive mail"):
        _validate("coach@nope-xyz.com")


def test_no_mx_but_a_record_is_accepted(monkeypatch):
    monkeypatch.setattr(email_check, "_resolve", _dns({("smallschool.org", "A"): ["203.0.113.5"]}))
    assert _validate("coach@smallschool.org") == "coach@smallschool.org"


def test_no_mx_and_no_address_is_rejected(monkeypatch):
    monkeypatch.setattr(email_check, "_resolve", _dns({}))
    with pytest.raises(email_check.EmailRejected):
        _validate("coach@parked-domain.com")


def test_null_mx_is_rejected(monkeypatch):
    monkeypatch.setattr(email_check, "_resolve", _dns({("nomail.com", "MX"): _mx(".")}))
    with pytest.raises(email_check.EmailRejected):
        _validate("coach@nomail.com")


@pytest.mark.parametrize("exc", [dns.exception.Timeout, dns.resolver.NoNameservers])
def test_dns_outage_accepts_rather_than_dropping_the_lead(exc, monkeypatch):
    monkeypatch.setattr(email_check, "_resolve", _dns({("coachmail.com", "MX"): exc}))
    assert _validate("coach@coachmail.com") == "coach@coachmail.com"


# ── HTTP: fake DB + slim app ────────────────────────────────────────────────
class _Result:
    def __init__(self, v):
        self.v = v

    def scalar_one_or_none(self):
        return self.v


class _DB:
    """Holds leads in memory. Answers the two queries the router makes."""
    def __init__(self):
        self.leads = []
        self.pending = []
        self.commits = 0

    async def execute(self, stmt, *_a, **_k):
        params = stmt.compile().params
        vals = set(params.values())
        if any("download_token" in k for k in params):
            hit = next((l for l in self.leads if l.download_token in vals and l.source in vals), None)
            return _Result(hit.id if hit else None)
        hit = next((l for l in self.leads if l.email.lower() in vals and l.source in vals), None)
        return _Result(hit)

    def add(self, obj):
        self.pending.append(obj)

    async def commit(self):
        for obj in self.pending:
            if obj.id is None:
                obj.id = uuid.uuid4()
            self.leads.append(obj)
        self.pending = []
        self.commits += 1

    async def rollback(self):
        self.pending = []


@pytest.fixture
def db():
    return _DB()


@pytest.fixture
def client(db, good_dns):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(lead_magnet.router)

    async def _get_db():
        yield db
    app.dependency_overrides[get_db] = _get_db
    limiter.reset()
    yield TestClient(app)
    limiter.reset()


def _form(**kw):
    base = dict(name="Test Coach", email="coach@coachmail.com", phone="", consent=True, website="")
    base.update(kw)
    return base


def test_lead_stored_with_source_and_timestamp_and_link_returned(client, db):
    r = client.post("/leads/halftime-pdf", json=_form(phone=None))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["download_path"].startswith("/leads/halftime-pdf/download/")
    assert len(db.leads) == 1
    lead = db.leads[0]
    assert lead.source == "halftime_pdf"
    assert lead.email == "coach@coachmail.com"
    assert lead.name == "Test Coach"
    assert lead.phone is None                      # optional, never required
    assert lead.created_at is not None
    assert lead.consent_email is True
    assert lead.consent_text == lead_magnet.CONSENT_TEXT
    assert body["download_path"].endswith(lead.download_token)


def test_phone_is_optional_but_stored_when_valid(client, db):
    assert client.post("/leads/halftime-pdf", json={"name": "Test Coach", "email": "coach@coachmail.com",
                                                    "consent": True}).status_code == 200
    assert db.leads[0].phone is None
    r = client.post("/leads/halftime-pdf", json=_form(email="aide@coachmail.com", phone="(555) 010-2030"))
    assert r.status_code == 200
    assert db.leads[1].phone == "(555) 010-2030"


@pytest.mark.parametrize("phone", ["call me", "123", "+1 555 010 2030 999 999", "555-010-2030 ext <b>"])
def test_junk_phone_rejected_with_optional_hint(client, db, phone):
    r = client.post("/leads/halftime-pdf", json=_form(phone=phone))
    assert r.status_code == 400
    assert "optional" in r.json()["detail"].lower()
    assert db.leads == []


@pytest.mark.parametrize("name", ["", "   ", "https://spam.example", "<script>"])
def test_name_required(client, db, name):
    r = client.post("/leads/halftime-pdf", json=_form(name=name))
    assert r.status_code == 400
    assert db.leads == []


def test_invalid_email_rejected_server_side(client, db):
    r = client.post("/leads/halftime-pdf", json=_form(email="coach@mailinator.com"))
    assert r.status_code == 400 and "disposable" in r.json()["detail"]
    r = client.post("/leads/halftime-pdf", json=_form(email="nope"))
    assert r.status_code == 400
    assert db.leads == []


def test_consent_required(client, db):
    r = client.post("/leads/halftime-pdf", json=_form(consent=False))
    assert r.status_code == 400
    assert db.leads == []


def test_honeypot_stores_nothing_and_returns_no_link(client, db):
    r = client.post("/leads/halftime-pdf", json=_form(website="http://bot.example"))
    assert r.status_code == 200
    assert r.json() == {"ok": True, "download_path": None}
    assert db.leads == [] and db.commits == 0


def test_repeat_email_reuses_one_row_and_link(client, db):
    a = client.post("/leads/halftime-pdf", json=_form()).json()
    b = client.post("/leads/halftime-pdf", json=_form(name="Test Coach Two", email="COACH@coachmail.com",
                                                      phone="555-010-2030")).json()
    assert a["download_path"] == b["download_path"]
    assert len(db.leads) == 1
    assert db.leads[0].name == "Test Coach Two"
    assert db.leads[0].phone == "555-010-2030"


def test_rate_limited(client, db):
    codes = [client.post("/leads/halftime-pdf", json=_form(email=f"c{i}@coachmail.com")).status_code
             for i in range(7)]
    assert codes[:5] == [200] * 5
    assert codes[5] == 429 and codes[6] == 429
    assert len(db.leads) == 5


def test_download_returns_the_pdf_for_a_valid_token(client, db):
    path = client.post("/leads/halftime-pdf", json=_form()).json()["download_path"]
    r = client.get(path)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "private, no-store"
    assert r.content.startswith(b"%PDF-1.4") and r.content.rstrip().endswith(b"%%EOF")


def test_download_unknown_token_404(client):
    assert client.get("/leads/halftime-pdf/download/not-a-real-token").status_code == 404


# ── the PDF itself ──────────────────────────────────────────────────────────
def test_pdf_is_well_formed_two_pages():
    pdf = halftime_sheet_pdf()
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.count(b"/Type /Page ") == 2
    # xref offsets point at real objects
    import re
    xref_at = int(re.search(rb"startxref\n(\d+)", pdf).group(1))
    assert pdf[xref_at:xref_at + 4] == b"xref"
    offsets = [int(m) for m in re.findall(rb"(\d{10}) 00000 n ", pdf)]
    for i, off in enumerate(offsets, start=1):
        assert pdf[off:].startswith(f"{i} 0 obj".encode())


def test_pdf_and_consent_copy_follow_the_fact_lock():
    text = halftime_sheet_pdf().decode("latin-1")
    for sport in ("Football / Flag Football", "Basketball"):
        assert sport in text
    assert "$7 USD, one time" in FOOTER_OFFER
    assert "Powered by Cosby AI Solutions" in text
    blob = (text + lead_magnet.CONSENT_TEXT).lower()
    for banned in ("sms", "text message", "free forever", "no card", "$0"):
        assert banned not in blob
    assert "Privacy Policy" in lead_magnet.CONSENT_TEXT
