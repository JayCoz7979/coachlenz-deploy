"""The migration runner applies forward SQL in filename order and skips rollbacks.

056 belongs to the upload fix. 057 is the waitlist. A *.down.sql file is a
hand-run reverse and must never be applied on the way up, including when both
files are in the folder together.
"""
import pathlib

import pytest


@pytest.mark.unit
def test_forward_files_skip_down_sql_and_run_056_then_057(tmp_path: pathlib.Path):
    names = [
        "057_marketing_lead_waitlist.down.sql",
        "056_games_r2_key_unique.sql",
        "057_marketing_lead_waitlist.sql",
        "056_games_r2_key_unique.down.sql",
    ]
    for name in names:
        (tmp_path / name).write_text("select 1;\n", encoding="utf-8")
    files = sorted(
        p for p in tmp_path.glob("*.sql") if not p.name.endswith(".down.sql")
    )
    assert [p.name for p in files] == [
        "056_games_r2_key_unique.sql",
        "057_marketing_lead_waitlist.sql",
    ]


@pytest.mark.unit
def test_runner_source_ignores_down_sql():
    source = (pathlib.Path(__file__).resolve().parents[2] / "backend" / "migrate.py").read_text(encoding="utf-8")
    assert 'not p.name.endswith(".down.sql")' in source
