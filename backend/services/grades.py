"""
Player Grades Board aggregation (Track 5.3) — pure and unit-testable.

The technique-grade pass stores per-play grades in each Event's extra_data as
`player_grades`: [{jersey, unit, grade, note}], where grade is a letter (often
prefixed like "B - held the pocket"). This module flattens those, converts letters
to points for averaging, and rolls them up by player, position group (unit), and
play type, plus a printable grade-sheet matrix.
"""
import csv
import io
from typing import Any, Dict, List, Optional

from backend.services.roster import normalize_jersey

LETTER_POINTS = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}
_POINTS_LETTER = [(3.5, "A"), (2.5, "B"), (1.5, "C"), (0.5, "D"), (-1.0, "F")]


def parse_grade_letter(grade: Any) -> Optional[str]:
    """Leading letter grade ('B - held the pocket' -> 'B'). Grades are emitted
    letter-first, so only the first character counts (avoids matching a stray letter
    later in a note)."""
    s = str(grade or "").strip().upper()
    return s[0] if s and s[0] in LETTER_POINTS else None


def points_to_letter(points: Optional[float]) -> Optional[str]:
    if points is None:
        return None
    for threshold, letter in _POINTS_LETTER:
        if points >= threshold:
            return letter
    return "F"


def _get(row: Any, field: str):
    return row.get(field) if isinstance(row, dict) else getattr(row, field, None)


def extract_player_grades(events) -> List[Dict[str, Any]]:
    """Flatten every graded player-play into rows: jersey, unit, letter, points,
    play_type, event_id, note. Events are Event rows (or dict stubs)."""
    rows: List[Dict[str, Any]] = []
    for e in events:
        extra = _get(e, "extra_data") or {}
        play_type = _get(e, "play_type") or "Unknown"
        eid = str(_get(e, "id") or "")
        for pg in (extra.get("player_grades") or []):
            if not isinstance(pg, dict):
                continue
            letter = parse_grade_letter(pg.get("grade"))
            if letter is None:
                continue
            rows.append({
                "jersey": normalize_jersey(pg.get("jersey")),
                "unit": (pg.get("unit") or "Unknown"),
                "letter": letter,
                "points": LETTER_POINTS[letter],
                "play_type": play_type,
                "event_id": eid,
                "note": pg.get("note"),
            })
    return rows


def _avg(points: List[float]) -> Optional[Dict[str, Any]]:
    if not points:
        return None
    avg = round(sum(points) / len(points), 2)
    return {"avg_points": avg, "letter": points_to_letter(avg), "n": len(points)}


def aggregate_grades(rows, roster_names: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Roll grade rows up by player, position group (unit), and play type."""
    roster_names = roster_names or {}
    by_player_pts: Dict[str, List[float]] = {}
    by_unit_pts: Dict[str, List[float]] = {}
    by_type_pts: Dict[str, List[float]] = {}
    player_unit: Dict[str, str] = {}
    for r in rows:
        j = r["jersey"]
        by_player_pts.setdefault(j, []).append(r["points"])
        by_unit_pts.setdefault(r["unit"], []).append(r["points"])
        by_type_pts.setdefault(r["play_type"], []).append(r["points"])
        player_unit.setdefault(j, r["unit"])
    by_player = {
        j: {"name": roster_names.get(j), "unit": player_unit.get(j), **_avg(pts)}
        for j, pts in by_player_pts.items()
    }
    return {
        "by_player": by_player,
        "by_position_group": {u: _avg(p) for u, p in by_unit_pts.items()},
        "by_play_type": {t: _avg(p) for t, p in by_type_pts.items()},
    }


def build_grade_sheet(rows, roster_names: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """The weekly-meeting sheet: players down the left, play types across the top,
    a grade in each cell, and position-group averages at the bottom."""
    roster_names = roster_names or {}
    play_types = sorted({r["play_type"] for r in rows})
    players = sorted({r["jersey"] for r in rows})
    player_unit: Dict[str, str] = {}
    cell_pts: Dict[str, Dict[str, List[float]]] = {}
    player_pts: Dict[str, List[float]] = {}
    unit_pts: Dict[str, List[float]] = {}
    for r in rows:
        j, t = r["jersey"], r["play_type"]
        player_unit.setdefault(j, r["unit"])
        cell_pts.setdefault(j, {}).setdefault(t, []).append(r["points"])
        player_pts.setdefault(j, []).append(r["points"])
        unit_pts.setdefault(r["unit"], []).append(r["points"])
    cells = {j: {t: _avg(pts) for t, pts in tmap.items()} for j, tmap in cell_pts.items()}
    return {
        "players": [{"jersey": j, "name": roster_names.get(j), "unit": player_unit.get(j)}
                    for j in players],
        "play_types": play_types,
        "cells": cells,
        "player_averages": {j: _avg(p) for j, p in player_pts.items()},
        "position_group_averages": {u: _avg(p) for u, p in unit_pts.items()},
    }


GRADE_CSV_COLUMNS = ["jersey", "name", "position_group"]


def grade_sheet_to_csv(sheet: Dict[str, Any]) -> str:
    """The grade sheet as CSV: one row per player, a column per play type, plus the
    player's overall, then position-group average rows at the bottom."""
    play_types = sheet["play_types"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(GRADE_CSV_COLUMNS + play_types + ["overall"])
    for p in sheet["players"]:
        j = p["jersey"]
        cells = sheet["cells"].get(j, {})
        row = [j, p.get("name") or "", p.get("unit") or ""]
        for t in play_types:
            c = cells.get(t)
            row.append(c["letter"] if c else "")
        pa = sheet["player_averages"].get(j)
        row.append(pa["letter"] if pa else "")
        w.writerow(row)
    w.writerow([])
    w.writerow(["Position group averages"])
    for unit, avg in sheet["position_group_averages"].items():
        w.writerow([unit, "", (avg["letter"] if avg else "")])
    return buf.getvalue()
