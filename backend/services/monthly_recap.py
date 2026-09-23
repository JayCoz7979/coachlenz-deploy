"""
Monthly recap (F3, value-lock 2026-09-23) — the forced, visible per-cycle win.

The subscription's biggest retention gap was that value only showed up when a coach
chose to run film; in a bye week or the off-season the app looked dead and the coach
questioned the bill. This builds a branded per-cycle recap of what CoachLenz already
did for them: films analyzed, plays broken down, hours saved, corrections applied
(surfacing the otherwise-invisible learning loop, F4), and credits remaining.

It reuses analysis the coach already paid for, so it costs NOTHING to produce (no new
vision run, no LLM call). The numbers are deterministic.

This module is PURE (no DB, no I/O) so it is fully unit-testable. The DB assembly and
the send live in the admin router / recap worker that call `compute_recap` +
`render_recap_html`.
"""
from typing import List, Dict, Any, Optional

# Conservative estimate of the hands-on time to break down ONE play by hand (rewind,
# log down/distance/formation/result, tag). 2 minutes is deliberately low so the
# "hours saved" number is defensible, not hype.
MANUAL_MIN_PER_PLAY = 2.0


def compute_recap(
    *,
    period_label: str,
    films_analyzed: int,
    plays_detected: int,
    corrections_applied: int,
    credits_remaining: int,
    top_labels: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Deterministic recap metrics. `top_labels` is a pre-counted list of
    {"label": str, "count": int}. `has_activity` drives whether the email reads as a
    win recap or an honest re-engagement nudge (we never congratulate a coach for a
    zero-film month)."""
    plays = max(0, int(plays_detected or 0))
    hours_saved = round(plays * MANUAL_MIN_PER_PLAY / 60.0, 1)
    return {
        "period_label": period_label,
        "films_analyzed": max(0, int(films_analyzed or 0)),
        "plays_detected": plays,
        "hours_saved": hours_saved,
        "corrections_applied": max(0, int(corrections_applied or 0)),
        "credits_remaining": max(0, int(credits_remaining or 0)),
        "top_labels": list(top_labels or [])[:3],
        "has_activity": (int(films_analyzed or 0) > 0 or plays > 0),
    }


def recap_subject(recap: Dict[str, Any]) -> str:
    if recap["has_activity"]:
        return (f"Your CoachLenz month: {recap['plays_detected']} plays broken down, "
                f"{recap['hours_saved']} hours saved")
    return "Your CoachLenz month: your credits are ready when you are"


# CGE brand: hunter green + gold accent, no blue.
_GREEN = "#14532d"
_GOLD = "#C9A84C"
_INK = "#1c1c1c"


def _stat(label: str, value: str) -> str:
    return (
        f"<td style='padding:10px 14px;text-align:center'>"
        f"<div style='font-size:26px;font-weight:800;color:{_GREEN}'>{value}</div>"
        f"<div style='font-size:12px;color:#666;text-transform:uppercase;letter-spacing:.04em'>{label}</div>"
        f"</td>"
    )


def render_recap_html(recap: Dict[str, Any], *, coach_name: str, org_name: str,
                      app_url: str = "https://app.coachlenz.com") -> str:
    """Branded recap email body. Honest on a zero-activity month (nudge, not a fake win)."""
    hi = f"Hi {coach_name}," if coach_name else "Hi coach,"
    footer = ("<p style='font-size:12px;color:#888;margin-top:28px'>Powered by "
              "<a href='https://cosbyaisolutions.com' style='color:#888'>Cosby AI Solutions</a></p>")

    if not recap["has_activity"]:
        return (
            f"<div style='font-family:system-ui,Arial,sans-serif;color:{_INK};max-width:560px'>"
            f"<p>{hi}</p>"
            f"<p>No film went through CoachLenz for {org_name} this cycle. That is the most "
            f"expensive kind of month, because the breakdown work is still waiting on you.</p>"
            f"<p>You have <strong style='color:{_GREEN}'>{recap['credits_remaining']} credits</strong> "
            f"ready to spend. Upload your next game and the full breakdown comes back in minutes.</p>"
            f"<p><a href='{app_url}' style='background:{_GREEN};color:#fff;padding:10px 18px;"
            f"border-radius:6px;text-decoration:none;font-weight:700'>Break down your next game</a></p>"
            f"{footer}</div>"
        )

    stats = (
        "<table style='border-collapse:collapse;margin:16px 0;width:100%'><tr>"
        + _stat("Films", str(recap["films_analyzed"]))
        + _stat("Plays broken down", str(recap["plays_detected"]))
        + _stat("Hours saved", str(recap["hours_saved"]))
        + "</tr></table>"
    )

    learning = ""
    if recap["corrections_applied"] > 0:
        learning = (
            f"<p>CoachLenz applied <strong style='color:{_GREEN}'>{recap['corrections_applied']}</strong> "
            f"of your label corrections this cycle. The analyzer is trained on how <em>you</em> see the "
            f"game, so every breakdown fits your system a little better than the last.</p>"
        )

    tendencies = ""
    if recap["top_labels"]:
        items = "".join(
            f"<li>{t.get('label')} - {t.get('count')}</li>" for t in recap["top_labels"]
        )
        tendencies = f"<p>Most-tagged this cycle:</p><ul style='color:{_INK}'>{items}</ul>"

    return (
        f"<div style='font-family:system-ui,Arial,sans-serif;color:{_INK};max-width:560px'>"
        f"<p>{hi}</p>"
        f"<p>Here is what CoachLenz did for {org_name} in {recap['period_label']}:</p>"
        f"{stats}"
        f"<p style='font-size:13px;color:#666;margin-top:-8px'>Hours saved assumes about "
        f"{MANUAL_MIN_PER_PLAY:g} minutes to break down each play by hand.</p>"
        f"{learning}"
        f"{tendencies}"
        f"<p>You have <strong style='color:{_GREEN}'>{recap['credits_remaining']} credits</strong> left. "
        f"<a href='{app_url}' style='color:{_GREEN};font-weight:700'>Open CoachLenz</a></p>"
        f"{footer}</div>"
    )
