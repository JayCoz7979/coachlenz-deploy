"""
Heat-map band mapping (Engine §12), shared by the Coach Layer and Player Layer.

Given a zone's eFG% and detection confidence, decide its color band. Two audiences:

  * Coach Layer — 4 bands (RED / ORANGE / YELLOW / GREEN) off the §12 eFG cutoffs.
  * Player Layer — 3 print-safe colors (Red = worry, Yellow = watch, Green = push
    them here), no numbers.

The hard §12 rule lives here: never paint a zone RED on a LOW-confidence read.
Single-camera film makes shaky reads; the map downgrades rather than overstate.
Pure and unit-testable; no framework, no DB.
"""
from typing import Optional, Dict, Any

# Below this mean detection confidence a zone is "low" — a RED is downgraded.
# Matches the escalation threshold used elsewhere (services.agent_log). Unknown
# (None) confidence is treated as not-high-enough-for-RED: we never assert a
# take-it-away zone we can't stand behind.
LOW_CONFIDENCE = 0.65

# Coach Layer: eFG% cutoffs -> band. Ordered high-to-low; first match wins.
_COACH_BANDS = [
    (55, "red", "#c0392b", "Take it away"),
    (45, "orange", "#d98c30", "Contest hard"),
    (35, "yellow", "#c9a227", "Standard defense"),
    (0, "green", "#1f7a3a", "Send them here"),
]

# Player Layer: 3 print-safe colors, plain labels, no numbers.
_PLAYER_RED = {"band": "red", "color": "#c0392b", "label": "Worry"}
_PLAYER_YELLOW = {"band": "yellow", "color": "#c9a227", "label": "Watch"}
_PLAYER_GREEN = {"band": "green", "color": "#1f7a3a", "label": "Push them here"}


def is_low_confidence(confidence: Optional[float]) -> bool:
    """True when a zone's read is too shaky to paint RED. Unknown counts as low."""
    if confidence is None:
        return True
    try:
        return float(confidence) < LOW_CONFIDENCE
    except (TypeError, ValueError):
        return True


def efg_band_coach(efg: Optional[float], confidence: Optional[float] = None) -> Dict[str, Any]:
    """Coach Layer 4-band mapping. A RED on a low-confidence zone is downgraded one
    step to ORANGE, with `downgraded` flagged so the UI can footnote it."""
    if efg is None:
        return {"band": "none", "color": "#8a8a80", "label": "No read", "downgraded": False}
    band, color, label = "green", "#1f7a3a", "Send them here"
    for cutoff, b, c, l in _COACH_BANDS:
        if efg >= cutoff:
            band, color, label = b, c, l
            break
    if band == "red" and is_low_confidence(confidence):
        return {"band": "orange", "color": "#d98c30", "label": "Contest hard", "downgraded": True}
    return {"band": band, "color": color, "label": label, "downgraded": False}


def efg_band_player(efg: Optional[float], confidence: Optional[float] = None) -> Dict[str, Any]:
    """Player Layer 3-color mapping, print-safe. RED on a low-confidence zone is
    downgraded to YELLOW (never overstate a take-away to a player)."""
    if efg is None:
        return {**_PLAYER_YELLOW, "downgraded": False}
    if efg >= 55:
        if is_low_confidence(confidence):
            return {**_PLAYER_YELLOW, "downgraded": True}
        return {**_PLAYER_RED, "downgraded": False}
    if efg >= 35:
        return {**_PLAYER_YELLOW, "downgraded": False}
    return {**_PLAYER_GREEN, "downgraded": False}
