"""
Monthly recap (F3) — pure engine tests: the hours-saved math, the honest zero-activity
path (a re-engagement nudge, never a fake "great month"), and the branded render.

Run:  python -m backend.tests.test_monthly_recap
"""
from backend.services import monthly_recap as R


def test_compute_recap_hours_saved_math():
    r = R.compute_recap(
        period_label="the last 30 days", films_analyzed=3, plays_detected=210,
        corrections_applied=12, credits_remaining=140,
        top_labels=[{"label": "run", "count": 90}, {"label": "pass", "count": 70}],
    )
    assert r["has_activity"] is True
    # 210 plays * 2.0 min / 60 = 7.0 hours
    assert r["hours_saved"] == 7.0
    assert r["films_analyzed"] == 3 and r["plays_detected"] == 210
    assert r["corrections_applied"] == 12 and r["credits_remaining"] == 140
    assert len(r["top_labels"]) == 2


def test_compute_recap_zero_activity_is_honest():
    r = R.compute_recap(
        period_label="the last 30 days", films_analyzed=0, plays_detected=0,
        corrections_applied=0, credits_remaining=45, top_labels=None,
    )
    assert r["has_activity"] is False
    assert r["hours_saved"] == 0.0
    # subject + body must NOT congratulate a zero-film month; they nudge with credits.
    assert "ready" in R.recap_subject(r).lower()
    html = R.render_recap_html(r, coach_name="Sam", org_name="Tanner")
    assert "45 credits" in html
    assert "break down your next game" in html.lower()


def test_render_is_branded_and_not_blue():
    r = R.compute_recap(
        period_label="the last 30 days", films_analyzed=2, plays_detected=100,
        corrections_applied=5, credits_remaining=60, top_labels=[{"label": "shot", "count": 40}],
    )
    html = R.render_recap_html(r, coach_name="Coach Lee", org_name="Lee HS")
    assert "Cosby AI Solutions" in html            # required credit
    assert "100" in html and "5" in html           # plays + corrections surfaced
    assert "3.3" in html                            # 100*2/60 = 3.33 -> 3.3 hours
    assert "blue" not in html.lower() and "navy" not in html.lower()
    # learning loop (F4) is surfaced when corrections exist
    assert "corrections" in html.lower()


def test_manual_estimate_is_conservative():
    # The hours-saved claim must stay defensible, not hype.
    assert R.MANUAL_MIN_PER_PLAY <= 3.0


def run():
    test_compute_recap_hours_saved_math()
    test_compute_recap_zero_activity_is_honest()
    test_render_is_branded_and_not_blue()
    test_manual_estimate_is_conservative()
    print("ALL MONTHLY-RECAP ASSERTIONS PASSED")


if __name__ == "__main__":
    run()
