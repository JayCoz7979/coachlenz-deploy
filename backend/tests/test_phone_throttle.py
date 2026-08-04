"""Finding #12: /auth/send-phone-code must throttle per user (60s cooldown +
daily cap) so it can't be looped to pump Twilio SMS to attacker-chosen numbers."""
from datetime import datetime, timedelta

from backend.services.twilio_verify import phone_send_allowed, PHONE_DAILY_LIMIT

NOW = datetime(2026, 8, 4, 12, 0, 0)


def test_first_send_is_allowed_and_counts_one():
    ok, new_count, reason = phone_send_allowed(last_sent=None, sent_today=0, now=NOW)
    assert ok is True and new_count == 1 and reason is None


def test_cooldown_blocks_rapid_resend():
    ok, _c, reason = phone_send_allowed(last_sent=NOW - timedelta(seconds=30),
                                        sent_today=1, now=NOW)
    assert ok is False and reason == "cooldown"


def test_after_cooldown_next_send_increments_same_day():
    ok, new_count, reason = phone_send_allowed(last_sent=NOW - timedelta(minutes=5),
                                               sent_today=2, now=NOW)
    assert ok is True and new_count == 3 and reason is None


def test_daily_cap_blocks_further_sends():
    ok, _c, reason = phone_send_allowed(last_sent=NOW - timedelta(minutes=10),
                                        sent_today=PHONE_DAILY_LIMIT, now=NOW)
    assert ok is False and reason == "daily"


def test_counter_resets_on_a_new_day():
    # Yesterday's count is spent, but a fresh day starts the counter over.
    ok, new_count, reason = phone_send_allowed(
        last_sent=NOW - timedelta(days=1), sent_today=PHONE_DAILY_LIMIT, now=NOW)
    assert ok is True and new_count == 1 and reason is None
