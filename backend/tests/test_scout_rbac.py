"""
RBAC teeth for the football dual-review gate (Gate 2).

Covers:
  • can_review_scout role matrix (who may sign off)
  • Gate 2 transitions on the scouting report as the scout_meta review state changes:
      draft (no reviewer)         -> Gate 2 FAILS
      reviewer == analyst          -> Gate 2 FAILS (no self-review)
      distinct reviewer + reviewed -> Gate 2 PASSES

Run:  DATABASE_URL=... SECRET_KEY=... ANTHROPIC_API_KEY=... python -m backend.tests.test_scout_rbac
"""
from types import SimpleNamespace

from backend.services.scout_roles import can_review_scout, SCOUT_REVIEWER_ROLES
from backend.services.tendency_engine.football import (
    analyze_football, analyze_football_defense, analyze_football_special,
)
from backend.services.tendency_engine.football_scout import build_football_scouting_report


def U(role):
    return SimpleNamespace(role=role)


def P(side="offense", **cols):
    direct = {}
    for k in ("down", "distance", "field_position", "hash_position", "formation",
              "personnel", "play_type", "motion", "result", "yards_gained",
              "time_seconds", "defensive_front", "coverage", "blitz"):
        direct[k] = cols.pop(k, None)
    direct["motion"] = bool(direct.get("motion"))
    return SimpleNamespace(event_type="play", side=side, extra_data=cols, **direct)


def META(**kw):
    return SimpleNamespace(event_type="scout_meta", side="meta", extra_data=kw,
                           down=None, distance=None, play_type=None)


def _plays():
    ev = []
    for i in range(12):
        ev.append(P(side="offense", game_number=(i % 3) + 1, down=1, distance=10,
                    formation="Shotgun", personnel="11", play_type="run",
                    run_concept="Inside Zone", yards_gained=4, result="gain"))
    return ev


def _gate2(meta):
    ev = [meta] + _plays()
    off = analyze_football([e for e in ev if e.side == "offense"])
    deff = analyze_football_defense([])
    st = analyze_football_special([])
    scouting = build_football_scouting_report(ev, off, deff, st)
    return {g["gate"]: g for g in scouting["validation_gates"]}[2]


def run():
    # ── role matrix ──────────────────────────────────────────────────────────
    for r in ("owner", "head_coach", "coordinator", "reviewer"):
        assert can_review_scout(U(r)) is True, f"{r} should be able to review"
    for r in ("member", "analyst", "", "random"):
        assert can_review_scout(U(r)) is False, f"{r} should NOT be able to review"
    print(f"  can_review roles: {sorted(SCOUT_REVIEWER_ROLES)} ✓")

    # ── Gate 2: fresh draft, no reviewer -> FAIL ─────────────────────────────
    g = _gate2(META(analyst_id="u1", analyst="Coach A", reviewer_id=None, status="draft"))
    assert g["passed"] is False, "draft with no reviewer must fail Gate 2"
    print(f"  draft/no-reviewer: passed={g['passed']} — {g['notes'][0]}")

    # ── Gate 2: reviewer is the analyst -> FAIL (no self-review) ─────────────
    g = _gate2(META(analyst_id="u1", analyst="Coach A", reviewer_id="u1",
                    reviewer="Coach A", status="reviewed"))
    assert g["passed"] is False, "self-review must fail Gate 2"
    print(f"  self-review:       passed={g['passed']}")

    # ── Gate 2: distinct reviewer, reviewed -> PASS ─────────────────────────
    g = _gate2(META(analyst_id="u1", analyst="Coach A", reviewer_id="u2",
                    reviewer="Coach B", status="reviewed"))
    assert g["passed"] is True, "distinct reviewer + reviewed must pass Gate 2"
    print(f"  distinct reviewer: passed={g['passed']} — {g['notes'][0]}")

    # ── Gate 2: distinct reviewer, final -> PASS ────────────────────────────
    g = _gate2(META(analyst_id="u1", analyst="Coach A", reviewer_id="u2",
                    reviewer="Coach B", status="final"))
    assert g["passed"] is True, "final with distinct reviewer must pass Gate 2"
    print(f"  final:             passed={g['passed']}")

    print("\nALL SCOUT RBAC ASSERTIONS PASSED")


if __name__ == "__main__":
    run()
