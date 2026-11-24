"""Acceptance checks for waitlist email. Resend is a fake gateway. No live calls."""
import asyncio
import inspect
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.config import settings
from backend.models.marketing_consent import EmailSuppression, MarketingConsentEvent
from backend.routers import funnel
from backend.services.waitlist_capture import active_consent
from backend.services import waitlist_email as mail


class _DB:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None

    async def execute(self, *_a, **_k):
        class _R:
            def scalar_one_or_none(self_inner):
                return None
        return _R()


class _Gateway:
    def __init__(self):
        self.sends = []
        self.contacts = []
        self.topics = []
        self.segments = []
        self.members = {}
        self.events = []
        self.unsubs = []

    def send(self, payload):
        self.sends.append(payload)
        return {"id": "msg_" + payload.get("kind", "x")}

    def upsert_contact(self, email, properties):
        self.contacts.append((email, properties))

    def subscribe_topic(self, email):
        self.topics.append(email)

    def add_to_segment(self, email, segment):
        self.segments.append((email, segment))
        self.members.setdefault(segment, set()).add(str(email).lower())

    def remove_from_segment(self, email, segment):
        self.segments.append(("remove", email, segment))
        self.members.setdefault(segment, set()).discard(str(email).lower())

    def send_event(self, name, email, properties):
        self.events.append((name, email, properties))

    def unsubscribe_contact(self, email, only_list):
        self.unsubs.append((email, only_list))


def _lead(**kw):
    base = dict(
        id="lead-1", email="Coach@School.edu", role="head_coach", role_branch="coach",
        school="Lincoln", sport="basketball", source="coachlenz-app-waitlist",
        lead_magnet="halftime-sheet-v1", utm_source="ig", utm_medium="social",
        utm_campaign="launch", utm_content="hero", utm_term="film",
        referrer="example.edu", created_at=datetime(2026, 11, 1, 12, 0, 0),
        confirmed_at=None, confirm_sent_at=None, confirm_token_hash=None,
        unsubscribed_at=None, reminder_sent_at=None, a1_sent_at=None,
        unsubscribe_token="unsub-tok", has_account=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def gw(monkeypatch):
    fake = _Gateway()
    mail.set_gateway(fake)
    monkeypatch.setattr(settings, "WAITLIST_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "WAITLIST_FROM_EMAIL", "waitlist@coachlenz.com")
    yield fake
    mail.set_gateway(None)


@pytest.mark.unit
def test_flag_off_makes_no_gateway_calls(monkeypatch):
    monkeypatch.setattr(settings, "WAITLIST_EMAIL_ENABLED", False)
    monkeypatch.setattr(settings, "WAITLIST_FROM_EMAIL", "waitlist@coachlenz.com")
    fake = _Gateway()
    mail.set_gateway(fake)
    lead = _lead()
    status = asyncio.run(mail.after_stored(_DB(), lead, {}))
    assert status == "stored_no_email"
    assert fake.sends == [] and fake.contacts == [] and fake.unsubs == []
    mail.set_gateway(None)


def _banned(text: str):
    lowered = text.lower()
    for word in ("pricing", "reward", "nurture", "sales", "ask your coach", "$"):
        assert word not in lowered


@pytest.mark.unit
def test_under_19_gets_c0_then_c1_then_launch_notice(gw):
    db = _DB()
    row = _lead(email="kid@school.edu", role="parent", role_branch="minor_track", sport=None)
    meta = {"ip": "203.0.113.8", "ua": "CoachBrowser"}
    assert asyncio.run(mail.after_stored(db, row, meta)) == "c0_sent"
    assert [s["kind"] for s in gw.sends] == ["C0"]
    assert gw.segments == [] and gw.topics == [] and gw.events == []
    assert asyncio.run(mail.send_launch_notice(db, row)) == "unconfirmed"
    assert [s["kind"] for s in gw.sends] == ["C0"]
    confirmed = asyncio.run(mail.confirm_token(db, row, meta))
    assert confirmed == "confirmed"
    assert [s["kind"] for s in gw.sends] == ["C0", "C1"]
    assert gw.sends[1]["template_key"] == "C1"
    _banned(gw.sends[1]["text"])
    assert mail.MINOR_SEGMENT == "CL Launch only: Minor track"
    added = [item for item in gw.segments if item[0] != "remove"]
    assert added == [
        (row.email, mail.ALL_CONFIRMED),
        (row.email, "CL Launch only: Minor track"),
    ]
    assert gw.events[0][0] == "coachlenz.waitlist.confirmed"
    assert gw.events[0][2]["role_branch"] == "minor_track"
    consent_rows = [obj for obj in db.added if isinstance(obj, MarketingConsentEvent)]
    signup = next(obj for obj in consent_rows if obj.event_type == "signup")
    confirmed_row = next(obj for obj in consent_rows if obj.event_type == "doi_confirmed")
    assert signup.ip_address == "203.0.113.8" and signup.user_agent == "CoachBrowser"
    assert confirmed_row.ip_address == "203.0.113.8" and confirmed_row.user_agent == "CoachBrowser"
    launched = asyncio.run(mail.send_launch_notice(db, row))
    assert launched == "l1m_sent"
    assert [s["kind"] for s in gw.sends] == ["C0", "C1", "L1-M"]
    assert gw.sends[2]["template_key"] == "L1-M"
    assert gw.sends[2]["segment"] == "CL Launch only: Minor track"
    _banned(gw.sends[2]["text"])
    assert asyncio.run(mail.send_launch_notice(db, row)) == "l1m_already_sent"
    assert len(gw.sends) == 3


@pytest.mark.unit
def test_unconfirmed_minor_track_gets_c0_and_no_delayed_send(gw):
    db = _DB()
    row = _lead(email="kid@school.edu", role="parent", role_branch="minor_track", sport=None)
    assert asyncio.run(mail.after_stored(db, row, {"ip": "198.51.100.8", "ua": "UA"})) == "c0_sent"
    now = row.confirm_sent_at + timedelta(hours=48)
    assert asyncio.run(mail.send_reminder(db, row, now)) == "exited"
    assert asyncio.run(mail.send_nurture_step(db, row, "n1")) == "exited"
    assert asyncio.run(mail.send_general_launch(db, row)) == "exited"
    assert asyncio.run(mail.send_launch_notice(db, row, now)) == "unconfirmed"
    assert [s["kind"] for s in gw.sends] == ["C0"]
    assert gw.segments == [] and gw.topics == [] and gw.events == [] and gw.contacts == []


@pytest.mark.unit
def test_exit_check_blocks_a_delayed_send_after_reclassification(gw):
    now = datetime(2026, 11, 20, 12, 0, 0)
    lead = _lead(
        role="head_coach", role_branch="coach", is_19_or_older=True,
        confirm_sent_at=now - timedelta(hours=48),
    )
    db = _DB()
    assert mail.reminder_due(lead, now) is True
    assert asyncio.run(mail.reclassify_as_minor(db, lead)) == "reclassified"
    assert lead.role_branch == "minor_track"
    assert asyncio.run(mail.send_reminder(db, lead, now)) == "exited"
    assert asyncio.run(mail.send_nurture_step(db, lead, "n1")) == "exited"
    assert asyncio.run(mail.send_general_launch(db, lead)) == "exited"
    assert gw.sends == []
    assert mail.reminder_due(lead, now) is True


@pytest.mark.unit
def test_reclassification_moves_segments_and_is_idempotent(gw, caplog):
    lead = _lead(role="head_coach", role_branch="coach", is_19_or_older=True)
    db = _DB()
    with caplog.at_level("INFO"):
        assert asyncio.run(mail.reclassify_as_minor(db, lead)) == "reclassified"
    removed = [("remove", lead.email, seg) for seg in list(mail.HOLDING_SEGMENTS) + [mail.LAUNCH_GENERAL]]
    assert gw.segments[:len(removed)] == removed
    assert gw.segments[-1] == (lead.email, "CL Launch only: Minor track")
    assert lead.reclass_log[0]["added"] == "CL Launch only: Minor track"
    assert "coach@school.edu" in caplog.text
    before = list(gw.segments)
    assert asyncio.run(mail.reclassify_as_minor(db, lead)) == "noop"
    assert gw.segments == before
    assert len(lead.reclass_log) == 1


@pytest.mark.unit
def test_player_19_or_older_follows_the_normal_path(gw):
    lead = _lead(role="player", role_branch="general", is_19_or_older=True)
    db = _DB()
    meta = {"ip": "203.0.113.8", "ua": "CoachBrowser"}
    assert asyncio.run(mail.after_stored(db, lead, meta)) == "c0_sent"
    assert asyncio.run(mail.confirm_token(db, lead, meta)) == "confirmed"
    assert [s["kind"] for s in gw.sends] == ["C0", "C1"]
    added = [item for item in gw.segments if item[0] != "remove"]
    assert added == [(lead.email, mail.ALL_CONFIRMED), (lead.email, mail.LAUNCH_GENERAL)]
    assert gw.events[0][2]["role_branch"] == "general"
    assert asyncio.run(mail.send_launch_notice(db, lead)) == "not_minor"
    assert [s["kind"] for s in gw.sends] == ["C0", "C1"]


@pytest.mark.unit
def test_unconfirmed_lead_never_enters_the_automation(gw):
    lead = _lead()
    db = _DB()
    status = asyncio.run(mail.after_stored(db, lead, {"ip": "203.0.113.8", "ua": "Test"}))
    assert status == "c0_sent"
    assert [s["kind"] for s in gw.sends] == ["C0"]
    assert gw.contacts == [] and gw.topics == [] and gw.segments == [] and gw.events == []
    assert "List-Unsubscribe" in gw.sends[0]["headers"]
    assert "promotion" not in gw.sends[0]["text"].lower()
    assert "https://app.coachlenz.com/privacy" in gw.sends[0]["text"]


@pytest.mark.unit
def test_resubmit_does_not_restart_or_send_a_second_a1(gw):
    now = datetime(2026, 11, 20, 12, 0, 0)
    lead = _lead(confirmed_at=now, a1_sent_at=now, confirm_sent_at=now)
    status = asyncio.run(mail.after_stored(_DB(), lead, {"now": now}))
    assert status == "already_confirmed"
    again = asyncio.run(mail.confirm_token(_DB(), lead, {"now": now}))
    assert again == "already_confirmed"
    assert gw.sends == [] and gw.contacts == []


@pytest.mark.unit
def test_unsubscribe_stops_coachlenz_only(gw):
    lead = _lead()
    db = _DB()
    status = asyncio.run(mail.unsubscribe_lead(db, lead))
    assert status == "unsubscribed"
    assert lead.unsubscribed_at is not None
    assert gw.unsubs == [(lead.email, mail.COACHLENZ_TOPIC)]
    assert all(item[1] == "CoachLenz updates" for item in gw.unsubs)
    suppression = [o for o in db.added if isinstance(o, EmailSuppression)]
    assert suppression and suppression[0].email_sha256 == mail.email_sha256(lead.email)
    # The suppression row does not depend on the lead object still existing.
    assert suppression[0].reason == "unsubscribe_link"


@pytest.mark.unit
def test_utms_land_on_the_lead_and_the_contact(gw):
    now = datetime(2026, 11, 20, 12, 0, 0)
    lead = _lead(confirm_sent_at=now - timedelta(hours=1))
    asyncio.run(mail.confirm_token(_DB(), lead, {"now": now, "ip": "203.0.113.9", "ua": "UA"}))
    assert gw.contacts, "contact upsert expected after confirm"
    _email, props = gw.contacts[0]
    assert props["utm_source"] == "ig"
    assert props["utm_medium"] == "social"
    assert props["utm_campaign"] == "launch"
    assert props["utm_content"] == "hero"
    assert props["utm_term"] == "film"
    assert lead.utm_source == "ig"


@pytest.mark.unit
def test_consent_event_stores_the_text_version_that_was_shown(gw):
    lead = _lead()
    db = _DB()
    asyncio.run(mail.after_stored(db, lead, {"ip": "198.51.100.4", "ua": "CoachBrowser"}))
    events = [o for o in db.added if isinstance(o, MarketingConsentEvent)]
    assert events
    event = events[0]
    pair = active_consent()
    assert event.event_type == "signup"
    assert event.consent_version == pair["version"] == "cl-halftime-v1"
    assert event.consent_text == pair["text"]
    assert event.consent_text.startswith("By clicking Send me the Halftime Sheet")
    assert "Button: Send me the Halftime Sheet" in event.consent_text
    assert event.consent_text_sha256 == pair["sha256"]
    assert event.email == "coach@school.edu"
    assert event.ip_address == "198.51.100.4"


@pytest.mark.unit
def test_pair_b_stores_its_own_line_button_and_version(monkeypatch, gw):
    monkeypatch.setattr(settings, "WAITLIST_CONSENT_PAIR", "b")
    lead = _lead()
    db = _DB()
    asyncio.run(mail.after_stored(db, lead, {"ip": "198.51.100.4", "ua": "CoachBrowser"}))
    event = [o for o in db.added if isinstance(o, MarketingConsentEvent)][0]
    pair = active_consent()
    assert pair["version"] == "cl-halftime-v1"
    assert pair["button"] == "Send me the Halftime Sheet"
    assert event.consent_version == "cl-halftime-v1"
    assert event.consent_text == pair["text"]
    assert event.consent_text.startswith("By clicking Send me the Halftime Sheet")
    assert "Button: Send me the Halftime Sheet" in event.consent_text
    assert event.consent_text_sha256 == pair["sha256"]
    assert "Join the waitlist" not in event.consent_text


@pytest.mark.unit
@pytest.mark.unit
def test_footer_address_passes_and_placeholder_is_refused():
    standard = mail.standard_footer()
    confirm = mail.confirmation_footer()
    assert mail.WAITLIST_POSTAL_ADDRESS in standard
    assert mail.WAITLIST_POSTAL_ADDRESS in confirm
    assert mail.WAITLIST_ENTITY in standard and mail.WAITLIST_ENTITY in confirm
    assert "https://app.coachlenz.com/privacy" in standard
    assert "https://app.coachlenz.com/privacy" in confirm
    mail.refuse_if_placeholder(standard)
    mail.refuse_if_placeholder(confirm)
    with pytest.raises(RuntimeError, match="placeholder"):
        mail.refuse_if_placeholder("CoachLenz is a product of [POSTAL ADDRESS, PENDING].")


@pytest.mark.unit
def test_resend_payload_has_no_ip_or_user_agent():
    lead = _lead()
    lead.ip_address = "203.0.113.9"
    lead.user_agent = "SecretBrowser"
    for payload in (mail.contact_properties(lead), mail.confirmed_event_properties(lead)):
        blob = str(payload).lower()
        assert "203.0.113.9" not in blob
        assert "secretbrowser" not in blob
        assert "ip_address" not in payload
        assert "user_agent" not in payload
    clean = mail.scrub_resend_payload({
        "kind": "C0", "text": mail.standard_footer(),
        "ip_address": "203.0.113.9", "user_agent": "SecretBrowser",
    })
    assert "ip_address" not in clean and "user_agent" not in clean
    assert mail._from_address() == "Jay Cosby <support@coachlenz.com>"
    assert mail._reply_to() == "support@coachlenz.com"


@pytest.mark.unit
def test_from_display_name_is_exactly_jay_cosby(monkeypatch):
    monkeypatch.delenv("WAITLIST_FROM", raising=False)
    monkeypatch.setattr(settings, "WAITLIST_EMAIL_ENABLED", True)
    fake = _Gateway()
    mail.set_gateway(fake)
    status = asyncio.run(mail.after_stored(
        _DB(), _lead(), {"ip": "203.0.113.8", "ua": "CoachBrowser"}))
    mail.set_gateway(None)
    assert status == "c0_sent"
    assert fake.sends[0]["from"] == "Jay Cosby <support@coachlenz.com>"
    assert fake.sends[0]["reply_to"] == "support@coachlenz.com"
    assert ", CoachLenz" not in fake.sends[0]["from"]


@pytest.mark.unit
def test_one_reminder_and_stale_pending_window():
    now = datetime(2026, 11, 20, 12, 0, 0)
    lead = _lead(confirm_sent_at=now - timedelta(hours=48))
    assert mail.reminder_due(lead, now) is True
    lead.reminder_sent_at = now
    assert mail.reminder_due(lead, now + timedelta(hours=1)) is False
    pending = _lead(created_at=now - timedelta(days=8), confirmed_at=None)
    assert mail.is_stale_pending(pending, now) is True
    confirmed = _lead(created_at=now - timedelta(days=8), confirmed_at=now)
    assert mail.is_stale_pending(confirmed, now) is False


def _confirm(lead):
    db = _DB()
    meta = {"ip": "203.0.113.8", "ua": "CoachBrowser"}
    asyncio.run(mail.after_stored(db, lead, meta))
    asyncio.run(mail.confirm_token(db, lead, meta))
    return db


@pytest.mark.unit
def test_confirm_routes_each_branch_to_its_segment(gw):
    coach = _lead(email="coach@school.edu", role="head_coach", role_branch="coach", sport="basketball")
    _confirm(coach)
    football = _lead(email="fb@school.edu", role="head_coach", role_branch="coach", sport="football")
    _confirm(football)
    admin = _lead(email="ad@school.edu", role="athletic_director", role_branch="admin", sport="basketball")
    _confirm(admin)
    general = _lead(email="parent@school.edu", role="parent", role_branch="general", sport=None)
    _confirm(general)
    minor = _lead(email="kid@school.edu", role="parent", role_branch="minor_track", sport=None)
    _confirm(minor)
    added = [item for item in gw.segments if item[0] != "remove"]
    def segs(email):
        return [seg for who, seg in added if who == email]
    assert segs(coach.email) == [mail.ALL_CONFIRMED, mail.HOLDING_COACHES]
    assert segs(football.email) == [mail.ALL_CONFIRMED, mail.HOLDING_COACHES_FOOTBALL]
    assert segs(admin.email) == [mail.ALL_CONFIRMED, mail.HOLDING_ADMIN]
    assert segs(general.email) == [mail.ALL_CONFIRMED, mail.LAUNCH_GENERAL]
    assert segs(minor.email) == [mail.ALL_CONFIRMED, "CL Launch only: Minor track"]
    kinds = {}
    for payload in gw.sends:
        kinds.setdefault(payload["to"], []).append(payload["kind"])
    assert kinds[coach.email] == ["C0"]
    assert kinds[admin.email] == ["C0"]
    assert kinds[general.email] == ["C0", "C1"]
    assert kinds[minor.email] == ["C0", "C1"]
    events = {email: props for _name, email, props in gw.events}
    assert events[coach.email] == {"role_branch": "coach"}
    assert events[football.email] == {"role_branch": "coach", "sport": "football"}
    assert events[minor.email]["role_branch"] == "minor_track"
    assert mail.path_name(coach) == "A" and mail.path_name(admin) == "B"


@pytest.mark.unit
def test_broadcast_guards_reject_the_record_and_the_name_general():
    with pytest.raises(RuntimeError, match="not a broadcast"):
        mail.broadcast("L1", mail.ALL_CONFIRMED)
    with pytest.raises(RuntimeError, match="General"):
        mail.guard_broadcast("General", "L1")
    with pytest.raises(RuntimeError, match="Minor track"):
        mail.broadcast("L1", mail.MINOR_SEGMENT)
    with pytest.raises(RuntimeError, match="only"):
        mail.broadcast("L1-M", mail.HOLDING_COACHES)
    with pytest.raises(RuntimeError, match="L2"):
        mail.broadcast("L2", mail.LAUNCH_GENERAL)


@pytest.mark.unit
def test_l1_broadcasts_once_per_adult_segment_and_l1m_is_minor_only(gw):
    sent = mail.broadcast_l1()
    assert [seg for seg, status in sent] == list(mail.L1_SEGMENTS)
    assert all(status == "sent" for _seg, status in sent)
    assert mail.broadcast_l1m() == "sent"
    targets = [payload["segment"] for payload in gw.sends]
    assert targets == [
        "CL Holding: Coaches",
        "CL Holding: Coaches Football",
        "CL Holding: Admin",
        "CL Launch only: General",
        "CL Launch only: Minor track",
    ]
    assert [payload["kind"] for payload in gw.sends] == ["L1", "L1", "L1", "L1", "L1-M"]
    assert mail.ALL_CONFIRMED not in targets
    assert "General" not in targets


@pytest.mark.unit
def test_l2_segment_excludes_accounts_minors_and_suppressed_and_rerun_is_noop(gw):
    coach = _lead(email="coach@school.edu", role_branch="coach", has_account=False)
    paid = _lead(email="paid@school.edu", role_branch="coach", has_account=True)
    football = _lead(email="fb@school.edu", role_branch="coach", sport="football", has_account=False)
    admin = _lead(email="ad@school.edu", role_branch="admin", has_account=False)
    minor = _lead(email="kid@school.edu", role_branch="minor_track", has_account=False)
    for lead, segment in (
        (coach, mail.HOLDING_COACHES),
        (paid, mail.HOLDING_COACHES),
        (football, mail.HOLDING_COACHES_FOOTBALL),
        (admin, mail.HOLDING_ADMIN),
        (minor, mail.HOLDING_COACHES),
    ):
        gw.add_to_segment(lead.email, segment)
    leads = [coach, paid, football, admin, minor]
    holding_before = {seg: set(gw.members[seg]) for seg in mail.HOLDING_SEGMENTS}
    preview = mail.rebuild_l2(leads, suppressed=["fb@school.edu"], dry_run=True)
    assert preview == {"members": 2, "add": 2, "remove": 0, "noop": False}
    assert mail.L2_SEGMENT not in gw.members
    written = mail.rebuild_l2(leads, suppressed=["fb@school.edu"], dry_run=False)
    assert written["members"] == 2 and written["noop"] is False
    assert gw.members[mail.L2_SEGMENT] == {"coach@school.edu", "ad@school.edu"}
    assert {seg: set(gw.members[seg]) for seg in mail.HOLDING_SEGMENTS} == holding_before
    ops_before = len(gw.segments)
    again = mail.rebuild_l2(leads, suppressed=["fb@school.edu"], dry_run=False)
    assert again["noop"] is True and again["add"] == 0 and again["remove"] == 0
    assert len(gw.segments) == ops_before
