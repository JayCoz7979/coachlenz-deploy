"""Finding #3: the per-coach monthly analysis cap is a count-then-insert, which
races under concurrency. The fix serializes billable runs with a FOR UPDATE read
of the coach's row before counting. This test pins the locking construct so the
guard can't silently regress to a plain (non-locking) SELECT.

Live concurrency serialization is a Postgres behavior (FOR UPDATE is a no-op on
SQLite), so it is validated by construction here and by code review, not by an
in-process race."""
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from backend.models.user import User


def test_coach_lock_read_compiles_to_for_update():
    stmt = select(User.id).where(User.id == "some-uuid").with_for_update()
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql.upper()


def test_ai_detect_source_locks_before_counting_usage():
    # The lock must appear in the trigger BEFORE the usage count, or it doesn't
    # serialize the count+insert it is meant to protect.
    import inspect
    import backend.routers.ai_detect as ai

    src = inspect.getsource(ai.trigger_auto_detect)
    lock_pos = src.find("with_for_update()")
    count_pos = src.find("select(func.count()).select_from(AnalysisUsage)")
    assert lock_pos != -1, "expected a FOR UPDATE lock in trigger_auto_detect"
    assert count_pos != -1
    assert lock_pos < count_pos, "the coach-row lock must precede the usage count"
