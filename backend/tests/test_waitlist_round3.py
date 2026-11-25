"""Round 3 QA fixes: unsubscribe token format check and Resend Broadcasts.

No test talks to Resend: the live gateway runs on an httpx MockTransport.
"""
import json
import secrets
import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import settings
from backend.models.base import get_db
from backend.ratelimit import limiter
from backend.routers import auth as auth_router
from backend.services import waitlist_email as mail
from backend.services.unsubscribe_token import is_valid_unsubscribe_token

SEGMENT_IDS = {name: f"seg-{i}" for i, name in enumerate(mail.ALL_SEGMENTS)}


# ---------- unsubscribe token format ----------

@pytest.mark.unit
def test_token_format_accepts_every_shape_the_code_issues():
    # models/user.py and waitlist_capture.py: secrets.token_urlsafe(32)
    for _ in range(50):
        assert is_valid_unsubscribe_token(secrets.token_urlsafe(32))
    # migration 055 backfill: gen_random_uuid() without dashes
    assert is_valid_unsubscribe_token(uuid.uuid4().hex)


@pytest.mark.unit
@pytest.mark.parametrize("bad", [
    "", "abc", "unsub-tok", "x" * 31, "x" * 65, "a" * 20 + " " + "b" * 20,
    "../../etc/passwd" + "a" * 20, "a" * 40 + "=", "a" * 40 + "%", "é" * 40, None, 123,
])
def test_token_format_rejects_shapes_no_issuer_makes(bad):
    assert not is_valid_unsubscribe_token(bad)


class _Result:
    def scalar_one_or_none(self):
        return None


class _DB:
    def __init__(self):
        self.queries = 0

    async def execute(self, *_a, **_k):
        self.queries += 1
        return _Result()

    async def commit(self):
        pass


def _client(db):
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(auth_router.router)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    return TestClient(app)


@pytest.mark.unit
def test_unsubscribe_rejects_a_malformed_token_without_a_lookup():
    limiter.reset()
    db = _DB()
    client = _client(db)
    for bad in ("", "abc", "DUMMY-r2fix", "x" * 65):
        res = client.post("/auth/unsubscribe", json={"token": bad})
        assert res.status_code == 400
        assert res.json()["detail"] == "This unsubscribe link isn't valid."
    assert db.queries == 0


@pytest.mark.unit
def test_unsubscribe_answers_the_same_for_any_well_formed_token():
    limiter.reset()
    db = _DB()
    client = _client(db)
    a = client.post("/auth/unsubscribe", json={"token": secrets.token_urlsafe(32)})
    b = client.post("/auth/unsubscribe", json={"token": uuid.uuid4().hex})
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json() == {"ok": True, "message": "You're unsubscribed from CoachLenz marketing emails."}
    assert db.queries == 4  # user and lead lookups for each, no match, same answer


# ---------- broadcasts use the Resend Broadcasts API ----------

def _live(monkeypatch, handler, enabled=True, configured=True):
    monkeypatch.setattr(settings, "WAITLIST_EMAIL_ENABLED", enabled)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_not_real" if configured else "")
    monkeypatch.setattr(settings, "WAITLIST_RESEND_TOPIC_ID", "topic-1" if configured else "")
    monkeypatch.setattr(settings, "WAITLIST_RESEND_SEGMENT_IDS", json.dumps(SEGMENT_IDS) if configured else "")
    monkeypatch.delenv("WAITLIST_FROM", raising=False)
    gw = mail.ResendGateway(transport=httpx.MockTransport(handler))
    mail.set_gateway(gw)
    return gw


@pytest.fixture(autouse=True)
def _reset_gateway():
    yield
    mail.set_gateway(None)


@pytest.mark.unit
def test_broadcast_is_a_no_op_with_email_off(monkeypatch):
    seen = []
    _live(monkeypatch, lambda r: seen.append(r) or httpx.Response(200, json={}), enabled=False)
    assert mail.broadcast_l1() == [(seg, "email_off") for seg in mail.L1_SEGMENTS]
    assert mail.broadcast_l1m() == "email_off"
    assert mail.broadcast_l2() == "email_off"
    assert seen == []


@pytest.mark.unit
def test_broadcast_refuses_until_configured(monkeypatch):
    seen = []
    _live(monkeypatch, lambda r: seen.append(r) or httpx.Response(200, json={}), configured=False)
    with pytest.raises(RuntimeError, match="not configured"):
        mail.broadcast_l2()
    assert seen == []


@pytest.mark.unit
def test_broadcasts_post_to_the_broadcasts_api_with_the_unsubscribe_tag(monkeypatch):
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path, json.loads(request.content), request.headers.get("authorization")))
        return httpx.Response(200, json={"object": "broadcast", "id": "bc-1"})

    _live(monkeypatch, handler)
    assert mail.broadcast_l1() == [(seg, "sent") for seg in mail.L1_SEGMENTS]
    assert mail.broadcast_l1m() == "sent"
    assert mail.broadcast_l2() == "sent"
    assert {(m, p) for m, p, _b, _a in seen} == {("POST", "/broadcasts")}
    segments = [b["segment_id"] for _m, _p, b, _a in seen]
    assert segments == [SEGMENT_IDS[s] for s in (*mail.L1_SEGMENTS, mail.MINOR_SEGMENT, mail.L2_SEGMENT)]
    assert SEGMENT_IDS[mail.ALL_CONFIRMED] not in segments
    for _m, _p, body, auth in seen:
        assert auth == "Bearer re_test_not_real"
        assert body["send"] is True
        assert body["topic_id"] == "topic-1"
        assert body["subject"] == "CoachLenz is opening"
        assert body["from"] and body["name"].startswith("CoachLenz ")
        assert mail.BROADCAST_UNSUBSCRIBE_TAG in body["text"]
        assert "to" not in body


@pytest.mark.unit
def test_send_broadcast_refuses_the_record_general_and_a_missing_tag(monkeypatch):
    seen = []
    gw = _live(monkeypatch, lambda r: seen.append(r) or httpx.Response(200, json={}))
    for segment in (mail.ALL_CONFIRMED, "General"):
        with pytest.raises(RuntimeError, match="Refusing"):
            gw.send_broadcast({"kind": "L1", "segment": segment, "text": mail.launch_text(broadcast=True)})
    with pytest.raises(RuntimeError, match="unsubscribe merge tag"):
        gw.send_broadcast({"kind": "L1", "segment": mail.HOLDING_ADMIN, "text": mail.launch_text("tok")})
    assert seen == []
