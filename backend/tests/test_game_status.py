"""
Regression guard for the games_status_check constraint drift.

The scouting routers insert a Game with status='manual'. That value must be in the
games_status_check CHECK set defined in the migrations, or the INSERT 500s in
Postgres. The model-based integration test cannot catch this (CHECK constraints
live in raw-SQL migrations, not the ORM model), so guard it statically: every
Game status literal the routers use must be in the latest allowed set.

Run:  python -m backend.tests.test_game_status
"""
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
ROUTERS = ROOT / "routers"


def latest_allowed_statuses():
    """Parse the most recent games_status_check CHECK (status IN (...)) list."""
    allowed = None
    for f in sorted(MIGRATIONS.glob("*.sql")):
        sql = f.read_text(encoding="utf-8")
        # Match a games_status_check definition and capture the IN (...) list.
        for m in re.finditer(r"games_status_check[\s\S]*?status\s+IN\s*\(([^)]*)\)", sql, re.IGNORECASE):
            vals = re.findall(r"'([^']+)'", m.group(1))
            if vals:
                allowed = set(vals)  # later migrations override earlier ones
        # Also handle the initial inline `status TEXT ... CHECK (status IN (...))` on games.
        if allowed is None and "CREATE TABLE" in sql and "games" in sql:
            gm = re.search(r"status\s+TEXT[^,]*CHECK\s*\(status\s+IN\s*\(([^)]*)\)\)", sql, re.IGNORECASE)
            if gm:
                allowed = set(re.findall(r"'([^']+)'", gm.group(1)))
    return allowed


def game_status_literals():
    """Every status="X" assigned on a Game(...) construction in the scout routers."""
    used = set()
    for name in ("scout.py", "scout_football.py"):
        src = (ROUTERS / name).read_text(encoding="utf-8")
        # Game(...) constructions may span lines; scan status="..." near Game(.
        for block in re.split(r"\bGame\s*\(", src)[1:]:
            head = block[:600]  # the constructor args
            mm = re.search(r'status\s*=\s*"([^"]+)"', head)
            if mm:
                used.add(mm.group(1))
    return used


def run():
    allowed = latest_allowed_statuses()
    assert allowed, "could not parse games_status_check allowed statuses from migrations"
    print(f"  allowed game statuses: {sorted(allowed)}")

    used = game_status_literals()
    print(f"  scout routers use Game status: {sorted(used)}")
    assert used, "expected to find at least one Game(status=...) in the scout routers"

    bad = used - allowed
    assert not bad, (
        f"scout routers use Game status {sorted(bad)} which is NOT in the "
        f"games_status_check set {sorted(allowed)} — add it via a migration or the "
        f"INSERT will fail in Postgres."
    )
    assert "manual" in allowed, "the scout flows rely on 'manual' being an allowed game status"

    print("\nGAME STATUS CONSTRAINT GUARD PASSED")


if __name__ == "__main__":
    run()
