"""
Guard for situational CSV enrichment — the coach's path to add down/distance to
AI-detected plays from scoreboard-less film WITHOUT duplicating or wiping plays.

Run:  python -m backend.tests.test_play_enrich
"""
from backend.services.play_enrich import (
    build_template_csv, parse_enrichment_csv, ENRICHABLE_FIELDS,
)


def _plays():
    return [
        {"event_id": "aaaaaaaa-0000-0000-0000-000000000001", "time_seconds": 60,
         "side": "offense", "formation": "Singleback", "personnel": "21",
         "play_type": "Run", "yards_gained": 4, "down": None, "distance": None,
         "field_position": None, "hash_position": None},
        {"event_id": "aaaaaaaa-0000-0000-0000-000000000002", "time_seconds": 73,
         "side": "special_teams", "formation": None, "personnel": None,
         "play_type": "Kickoff", "yards_gained": None, "down": None, "distance": None,
         "field_position": None, "hash_position": None},
    ]


def run():
    # 1. Template round-trips: header carries event_id + play_index + enrichable cols;
    #    a detected value is preserved, missing ones are blank.
    csv_text = build_template_csv(_plays())
    header = csv_text.splitlines()[0]
    for col in ("event_id", "play_index", *ENRICHABLE_FIELDS):
        assert col in header, f"template missing column {col}"
    assert "Singleback" in csv_text and "Kickoff" in csv_text

    # 2. A filled template parses: event_id key, down/distance coerced to ints.
    filled = (
        "event_id,play_index,down,distance,hash_position\n"
        "aaaaaaaa-0000-0000-0000-000000000001,1,1,10,left\n"
        "aaaaaaaa-0000-0000-0000-000000000002,2,,,\n"  # all blank -> dropped
    )
    p = parse_enrichment_csv(filled)
    assert p["header_error"] is None, p["header_error"]
    assert len(p["rows"]) == 1, p["rows"]
    r = p["rows"][0]
    assert r["key_type"] == "event_id" and r["key"].endswith("0001")
    assert r["fields"] == {"down": 1, "distance": 10, "hash_position": "left"}, r["fields"]

    # 3. Validation: out-of-range down and bad hash are row errors, not silent drops.
    bad = "event_id,down,distance,hash_position\nx,5,200,sideways\n"
    r = parse_enrichment_csv(bad)["rows"][0]
    assert any("down 5" in e for e in r["errors"]), r["errors"]
    assert any("distance 200" in e for e in r["errors"]), r["errors"]
    assert any("hash" in e for e in r["errors"]), r["errors"]

    # 4. play_index fallback works when there is no event_id column.
    p = parse_enrichment_csv("play_index,down,distance\n3,3,2\n")
    assert p["header_error"] is None
    assert p["rows"][0]["key_type"] == "play_index" and p["rows"][0]["key"] == 3

    # 5. Header aliases: Hudl-ish names map (Dn/ToGo), and a detection label column
    #    (Formation) is IGNORED — enrichment can never overwrite AI reads.
    p = parse_enrichment_csv("event_id,Dn,ToGo,Formation\nz,2,7,Trips\n")
    assert p["header_error"] is None
    assert p["rows"][0]["fields"] == {"down": 2, "distance": 7}, p["rows"][0]["fields"]
    assert "formation" not in p["colmap"]

    # 6. Missing key column -> fatal header error (can't match plays).
    p = parse_enrichment_csv("down,distance\n1,10\n")
    assert p["header_error"] and "match" in p["header_error"].lower(), p

    # 7. No enrichable column -> fatal header error (nothing to set).
    p = parse_enrichment_csv("event_id,formation\nz,Trips\n")
    assert p["header_error"] and "enrichable" in p["header_error"].lower(), p

    # 8. field_position passes through (trimmed); blank distance leaves it unset.
    p = parse_enrichment_csv("event_id,down,field_position\nz,1,OWN 35\n")
    assert p["rows"][0]["fields"] == {"down": 1, "field_position": "OWN 35"}, p["rows"][0]["fields"]

    print("PLAY ENRICH GUARD PASSED")


if __name__ == "__main__":
    run()
