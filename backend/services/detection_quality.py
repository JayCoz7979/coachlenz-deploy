"""
The detection-quality gate.

The retention / conversion / traffic gates measure whether coaches show up and
stay. This measures the thing the whole product rests on: does the film agent
actually chop the plays right, and fast. "Top notch" is meaningless until it is a
number, so this turns it into one, the same discipline, applied to detection.

Two questions, from our OWN data, no new table:

  RECALL ("did we find every snap") — the complaint that it misses plays.
    Proxy = auto-detected plays / all plays that ended up on the game. A play the
    coach had to add by hand is a snap the agent missed. This is a FLOOR: it only
    counts misses a coach bothered to fix, so true recall is <= the proxy. Pass an
    admin-confirmed `true_plays` for a game and the proxy upgrades to a real recall
    number (labeled measurement) for that game.

  LABEL QUALITY ("did we tag it right") — corrections per auto-detected play and
    the needs-your-eyes rate. High edit rate = the agent found the play but
    mislabeled it.

  TIMELINESS ("how fast") — wall-clock vs film length and seconds per play, from
    the measured cost log. Reported, not pass/failed: we have no defensible SLA
    until there is real turnaround data to set one honestly.

The killer cut is by FILM QUALITY (HD vs SD ingest). Our own ceiling says low-res
single-cam film has worse recall; this proves or disproves that from real runs, so
the "curate the first coach's film" rule stands on data, not a hunch.

Pure and deterministic (no DB, no model call) so it is fully unit-testable; the
admin router assembles the per-game rows and calls build_scorecard().
"""
from statistics import median
from typing import Any, Dict, List, Optional

# The bar for "a true 90%". Recall is the gated number here.
RECALL_PASS = 0.90    # chops >= 90% of snaps -> top notch
RECALL_WATCH = 0.75   # 75-90% -> usable but coaches will notice misses
# Label quality: corrections per auto-detected play. Lower is better.
LABEL_EDIT_WATCH = 0.15   # >15% of plays get a label fixed -> watch
LABEL_EDIT_STOP = 0.30    # >30% -> the tagging is not trustworthy yet
# Film-quality buckets by ingested video height (< 720 = SD, jersey/read-limited).
HD_MIN_HEIGHT = 720


def _hd_bucket(film_height: Optional[int]) -> str:
    if film_height is None or film_height <= 0:
        return "unknown"
    return "hd" if film_height >= HD_MIN_HEIGHT else "sd"


def _recall_verdict(recall: Optional[float], plays: int) -> str:
    if not plays or recall is None:
        return "no_data"
    if recall >= RECALL_PASS:
        return "pass"
    if recall >= RECALL_WATCH:
        return "watch"
    return "stop"


def _label_verdict(edit_rate: Optional[float], auto_plays: int) -> str:
    if not auto_plays or edit_rate is None:
        return "no_data"
    if edit_rate <= LABEL_EDIT_WATCH:
        return "pass"
    if edit_rate <= LABEL_EDIT_STOP:
        return "watch"
    return "stop"


def _score_game(g: Dict[str, Any]) -> Dict[str, Any]:
    auto = int(g.get("auto_plays") or 0)
    coach_added = int(g.get("coach_added_plays") or 0)
    corrections = int(g.get("corrections") or 0)
    needs_review = int(g.get("needs_review") or 0)
    true_plays = g.get("true_plays")
    total = auto + coach_added

    # Denominator: an admin-confirmed true count sharpens the proxy into a real
    # recall number; otherwise the coach-added floor.
    labeled = isinstance(true_plays, int) and true_plays > 0
    denom = true_plays if labeled else total
    recall = round(auto / denom, 4) if denom else None

    # Basketball shot-scoped recall: detected FIELD-GOAL attempts vs a true FGA count.
    # Apples-to-apples for basketball, where the all-event recall above does not
    # match a scorebook. shots_detected excludes free throws upstream (see admin.py)
    # so it matches the coach's FGA. Only meaningful when a true FGA count is set.
    shots_detected = int(g.get("shots_detected") or 0)
    true_shots = g.get("true_shots")
    shot_labeled = isinstance(true_shots, int) and true_shots > 0
    shot_recall = round(shots_detected / true_shots, 4) if shot_labeled else None
    shot_verdict = _recall_verdict(shot_recall, true_shots if shot_labeled else 0)

    elapsed = g.get("elapsed_seconds")
    film_secs = g.get("film_seconds")
    realtime_ratio = (round(elapsed / film_secs, 3)
                      if elapsed and film_secs and film_secs > 0 else None)
    sec_per_play = round(elapsed / total, 1) if elapsed and total else None
    edit_rate = round(corrections / auto, 4) if auto else None

    return {
        "game_id": g.get("game_id"),
        "title": g.get("title"),
        "game_date": g.get("game_date"),
        "sport": (g.get("sport") or "football").lower(),
        "film_quality": _hd_bucket(g.get("film_height")),
        "film_height": g.get("film_height"),
        "auto_plays": auto,
        "coach_added_plays": coach_added,
        "total_plays": total,
        "true_plays": true_plays if labeled else None,
        "measurement": "labeled" if labeled else "proxy",
        "recall": recall,
        "recall_verdict": _recall_verdict(recall, denom or 0),
        "shots_detected": shots_detected,
        "true_shots": true_shots if shot_labeled else None,
        "shot_recall": shot_recall,
        "shot_recall_verdict": shot_verdict,
        "corrections": corrections,
        "label_edit_rate": edit_rate,
        "label_verdict": _label_verdict(edit_rate, auto),
        "needs_review": needs_review,
        "needs_review_rate": round(needs_review / auto, 4) if auto else None,
        "avg_confidence": g.get("avg_confidence"),
        "elapsed_seconds": elapsed,
        "film_seconds": film_secs,
        "realtime_ratio": realtime_ratio,
        "sec_per_play": sec_per_play,
    }


def _aggregate(games: List[Dict[str, Any]], label: str) -> Dict[str, Any]:
    """Roll a set of per-game scores into one bucket verdict. Recall is pooled
    play-weighted (sum of found / sum of denominators), so a 200-play game counts
    more than a 12-play clip, which is the honest way to read recall."""
    auto = sum(g["auto_plays"] for g in games)
    coach_added = sum(g["coach_added_plays"] for g in games)
    corrections = sum(g["corrections"] for g in games)
    needs_review = sum(g["needs_review"] for g in games)
    # Pooled recall denominator: true_plays where labeled, else total.
    denom = sum((g["true_plays"] if g["measurement"] == "labeled" and g["true_plays"]
                 else g["total_plays"]) for g in games)
    any_labeled = any(g["measurement"] == "labeled" for g in games)
    recall = round(auto / denom, 4) if denom else None
    edit_rate = round(corrections / auto, 4) if auto else None
    # Pooled basketball shot recall over the games that have a true FGA count.
    shots_detected = sum(g["shots_detected"] for g in games)
    shot_true = sum(g["true_shots"] for g in games if g["true_shots"])
    shot_recall = round(
        sum(g["shots_detected"] for g in games if g["true_shots"]) / shot_true, 4
    ) if shot_true else None
    ratios = [g["realtime_ratio"] for g in games if g["realtime_ratio"] is not None]
    confs = [g["avg_confidence"] for g in games if g["avg_confidence"] is not None]
    return {
        "label": label,
        "games": len(games),
        "auto_plays": auto,
        "coach_added_plays": coach_added,
        "total_plays": auto + coach_added,
        "measurement": "labeled" if any_labeled else "proxy",
        "recall": recall,
        "recall_verdict": _recall_verdict(recall, denom),
        "shots_detected": shots_detected,
        "shot_recall": shot_recall,
        "shot_recall_verdict": _recall_verdict(shot_recall, shot_true),
        "corrections": corrections,
        "label_edit_rate": edit_rate,
        "label_verdict": _label_verdict(edit_rate, auto),
        "needs_review": needs_review,
        "needs_review_rate": round(needs_review / auto, 4) if auto else None,
        "avg_confidence": round(sum(confs) / len(confs), 3) if confs else None,
        "median_realtime_ratio": round(median(ratios), 3) if ratios else None,
    }


def build_scorecard(games: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Given per-game rows, return the detection-quality scorecard: an overall
    verdict, per-film-quality buckets (the HD-vs-SD cut), and the per-game detail,
    newest first as the caller ordered them."""
    scored = [_score_game(g) for g in games]

    buckets: Dict[str, List[Dict[str, Any]]] = {"hd": [], "sd": [], "unknown": []}
    for s in scored:
        buckets[s["film_quality"]].append(s)

    by_film_quality = [
        _aggregate(rows, name) for name, rows in
        (("HD film (>=720p)", buckets["hd"]),
         ("SD film (<720p)", buckets["sd"]),
         ("Unknown resolution", buckets["unknown"]))
        if rows
    ]

    overall = _aggregate(scored, "All analyzed film") if scored else {
        "label": "All analyzed film", "games": 0, "auto_plays": 0,
        "coach_added_plays": 0, "total_plays": 0, "measurement": "proxy",
        "recall": None, "recall_verdict": "no_data", "shots_detected": 0,
        "shot_recall": None, "shot_recall_verdict": "no_data", "corrections": 0,
        "label_edit_rate": None, "label_verdict": "no_data", "needs_review": 0,
        "needs_review_rate": None, "avg_confidence": None,
        "median_realtime_ratio": None,
    }

    return {
        "recall_pass_bar": RECALL_PASS,
        "recall_watch_line": RECALL_WATCH,
        "label_edit_watch": LABEL_EDIT_WATCH,
        "label_edit_stop": LABEL_EDIT_STOP,
        "overall": overall,
        "by_film_quality": by_film_quality,
        "games": scored,
    }
