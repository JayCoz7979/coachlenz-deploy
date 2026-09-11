"""
Run preservation — a re-run must NEVER silently lose the prior AI run's plays.

The detector snapshots the prior auto-detected events into an AnalysisRunArchive
(ARCHIVE_EVENT_COLUMNS) before clearing them. This guard proves the snapshot column
set stays complete: if a new Event data column is added but not added to
ARCHIVE_EVENT_COLUMNS, a restored run would silently drop it — so this test fails
loudly and forces the column to be included.

Run:  python -m backend.tests.test_analysis_run_archive
"""
from backend.models.event import Event
from backend.models.analysis_run import ARCHIVE_EVENT_COLUMNS

# Identity / FK / derived columns that are set fresh on restore, never snapshotted.
_NOT_SNAPSHOTTED = {"id", "game_id", "organization_id", "clip_id", "created_at"}


def run():
    all_cols = {c.name for c in Event.__table__.columns}
    snap = set(ARCHIVE_EVENT_COLUMNS)

    # Every archive column is a real Event column.
    unknown = snap - all_cols
    assert not unknown, f"ARCHIVE_EVENT_COLUMNS names non-existent Event columns: {unknown}"

    # Every data-bearing Event column is captured (nothing silently dropped on restore).
    missing = all_cols - snap - _NOT_SNAPSHOTTED
    assert not missing, (
        "These Event columns would be LOST on run-restore. Add them to "
        f"ARCHIVE_EVENT_COLUMNS (or to _NOT_SNAPSHOTTED if truly derived): {missing}"
    )

    # The two sets must not overlap (a column is either snapshotted or fresh, not both).
    overlap = snap & _NOT_SNAPSHOTTED
    assert not overlap, f"Columns marked both snapshotted and fresh: {overlap}"

    print(f"  ARCHIVE_EVENT_COLUMNS covers all {len(snap)} data columns; "
          f"{len(_NOT_SNAPSHOTTED)} identity/derived columns set fresh on restore ✓")
    print("\nALL RUN-ARCHIVE ASSERTIONS PASSED")


def test_archive_columns_complete():
    run()


if __name__ == "__main__":
    run()
