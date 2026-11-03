"""
DETERMINISTIC SYNTHETIC FIXTURE for basketball possession-context tests.

THIS IS A FIXTURE, NOT REAL RECALL EVIDENCE. The events below were hand-authored
to exercise the possession-context layer and the action-aware dedup. They are not
drawn from any real game, carry no measured recall number, and must never be cited
as proof of detection accuracy. A real basketball recall figure requires a labeled
clip run through the detector (a separate, approval-gated paid step).

Event dict shape mirrors a detected play (pre-persist): time_seconds, event_type,
side, result, confidence, player, shot_zone, quarter.
"""

# Clean possession sequence (already deduped) for possession + review tests.
# Scouted team = offense/transition; opponent = defense.
POSSESSION_EVENTS = [
    {"time_seconds": 10.0, "event_type": "shot", "side": "offense", "result": "missed",
     "confidence": 0.90, "player": "5", "shot_zone": "Wing 3", "quarter": 1},
    {"time_seconds": 22.0, "event_type": "rebound", "side": "offense", "result": None,
     "confidence": 0.80, "player": "22", "quarter": 1},
    {"time_seconds": 24.0, "event_type": "shot", "side": "offense", "result": "made",
     "confidence": 0.85, "player": "22", "shot_zone": "Restricted Area", "quarter": 1},
    {"time_seconds": 40.0, "event_type": "shot", "side": "defense", "result": "made",
     "confidence": 0.88, "quarter": 1},
    {"time_seconds": 58.0, "event_type": "shot", "side": "offense", "result": "made",
     "confidence": 0.90, "player": "10", "shot_zone": "Top of Key", "quarter": 1},
    {"time_seconds": 74.0, "event_type": "turnover", "side": "offense", "result": None,
     "confidence": 0.60, "player": "5", "quarter": 1},   # low confidence -> review queue
    {"time_seconds": 92.0, "event_type": "shot", "side": "offense", "result": "made",
     "confidence": 0.90, "player": "10", "quarter": 1},  # scouted again, opp possession undetected
    {"time_seconds": 410.0, "event_type": "shot", "side": "offense", "result": "made",
     "confidence": 0.70, "player": "5", "quarter": 2},   # Q2
]

# Raw detections (pre-dedup) for the action-aware dedup tests.
#   - 22.0 miss / 24.0 made putback: DISTINCT actions 2s apart (miss vs make,
#     different player) -> must both survive.
#   - 58.0 / 59.4 made by #10 from Top of Key: the SAME action seen twice -> merge.
#   - 80.0: a separate later make.
RAW_DETECTIONS = [
    {"time_seconds": 22.0, "event_type": "shot", "side": "offense", "result": "missed",
     "confidence": 0.85, "player": "5", "shot_zone": "Restricted Area"},
    {"time_seconds": 24.0, "event_type": "shot", "side": "offense", "result": "made",
     "confidence": 0.80, "player": "22", "shot_zone": "Restricted Area"},
    {"time_seconds": 58.0, "event_type": "shot", "side": "offense", "result": "made",
     "confidence": 0.70, "player": "10", "shot_zone": "Top of Key"},
    {"time_seconds": 59.4, "event_type": "shot", "side": "offense", "result": "made",
     "confidence": 0.90, "player": "10", "shot_zone": "Top of Key"},
    {"time_seconds": 80.0, "event_type": "shot", "side": "offense", "result": "made",
     "confidence": 0.90, "player": "5"},
]
