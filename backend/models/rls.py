"""
Per-request org context for the Row Level Security backstop.

Stage 2 of the plan in docs/security/rls-backstop-plan.md. A ContextVar carries
the current request's (or worker job's) organization id, and a SQLAlchemy
`after_begin` listener stamps it into the Postgres session GUC `app.org_id` at the
start of every transaction, so RLS policies (`current_setting('app.org_id')`) can
scope every query to that org.

DORMANT by default. The listener is a no-op unless `settings.RLS_ENABLED` is true
AND the dialect is postgresql, so it changes nothing on SQLite (the test harness)
and nothing in production until the staged cutover flips the flag. Setting the
ContextVar itself is always cheap and harmless; its value is only ever read once
enforcement is switched on.

Why transaction-local: `set_config(..., true)` clears the GUC automatically at
COMMIT/ROLLBACK, so a pooled connection can never carry one request's org into the
next. The listener re-applies on every transaction, which is required because the
app commits mid-request and each commit starts a fresh transaction.
"""
import contextvars

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from backend.config import settings

# None outside a request, or for a cross-org context (e.g. a worker polling the
# job queue) that must not be pinned to a single org.
_current_org: contextvars.ContextVar = contextvars.ContextVar(
    "coachlenz_current_org", default=None
)


def set_org_context(org_id) -> None:
    """Bind the current async task / request / worker job to an org for RLS."""
    _current_org.set(str(org_id) if org_id else None)


def get_org_context():
    return _current_org.get()


def reset_org_context() -> None:
    """Clear the org binding (e.g. after a worker finishes a job)."""
    _current_org.set(None)


@event.listens_for(Session, "after_begin")
def _apply_org_guc(session, transaction, connection) -> None:
    """Stamp app.org_id into the DB session at the start of each transaction.

    No-op unless RLS is enabled and the backend is Postgres. An empty context sets
    app.org_id to '' which matches no org row (fail-closed under the policies)."""
    if not getattr(settings, "RLS_ENABLED", False):
        return
    if connection.dialect.name != "postgresql":
        return
    org = get_org_context() or ""
    connection.execute(
        text("SELECT set_config('app.org_id', :org, true)"), {"org": org}
    )
