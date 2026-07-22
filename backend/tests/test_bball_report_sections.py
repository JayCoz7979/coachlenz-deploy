"""
Guard: the basketball report must include a Shot Chart (heat map) and Key Players
section when that data was read off the film — and must NOT sprout empty ones when
it wasn't. These sections drive the LLM prose, so if the spec drops them the coach's
report silently loses its heat map and player callouts.

Run:  python -m backend.tests.test_bball_report_sections
"""
from backend.services.report_writer import _bball_sections


def _headings(scouting, summary):
    return [s["heading"] for s in _bball_sections(scouting, summary)]


def main():
    ok = True

    def check(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")

    # Full data: shot zones read + at least one legible jersey.
    full = {
        "shot_zone_map": {"zones": {
            "Restricted Area": {"attempts": 20, "made": 12, "fg_pct": 60.0, "pct_of_all_shots": 30.0},
            "Left Corner 3": {"attempts": 8, "made": 4, "fg_pct": 50.0, "pct_of_all_shots": 12.0},
        }, "hottest_zone": "Restricted Area", "most_frequent_zone": "Restricted Area"},
        "shooting_overview": {"total_shots": 66, "overall_fg_pct": 44.0},
        "player_tendencies": {"tracked": True, "players_identified": 3,
                              "by_player": {"offense#3": {"jersey": "3", "team": "offense", "as_primary": 18}}},
    }
    h = _headings({}, full)
    check("Shot Chart section present when zones exist", any("Shot Chart" in x for x in h))
    check("Key Players section present when a jersey is tracked", any("Key Players" in x for x in h))

    # No player data (unreadable jerseys) → no Key Players section, but zones still map.
    no_players = dict(full, player_tendencies={"tracked": False, "players_identified": 0})
    h = _headings({}, no_players)
    check("Key Players omitted when no jersey tracked", not any("Key Players" in x for x in h))
    check("Shot Chart still present", any("Shot Chart" in x for x in h))

    # No shot zones (thin breakdown) → no Shot Chart section.
    no_zones = dict(full, shot_zone_map={})
    h = _headings({}, no_zones)
    check("Shot Chart omitted when no zones read", not any("Shot Chart" in x for x in h))

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
