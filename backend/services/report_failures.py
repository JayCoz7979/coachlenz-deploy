"""
Report-generation failure classification + status (pure, unit-testable).

Splits a failure into two audiences, per the product rule:
  * the coach (client) only ever sees a gentle, generic message + Retry
  * the founder/admin gets the real reason (e.g. the Anthropic usage-limit text),
    via logs and a deduped ops email

A report row is "failed" when generation errored (error_reason set) and it never
finished (generated_at is null). This is what lets the UI stop the infinite
"Analyzing…" spinner and offer a retry.
"""

# Shown to the coach. Never leak the underlying billing/API detail here.
CLIENT_FAILURE_MESSAGE = "This report couldn't be generated. Please try again in a few minutes."

# Substrings that mark a provider usage / credit / rate limit — the class of failure
# the founder wants to be alerted about (top up or raise the cap).
_QUOTA_MARKERS = ("usage limit", "credit balance", "rate limit", "quota", "insufficient", "billing")


def report_status(generated_at, error_reason) -> str:
    """One of: ready | failed | generating."""
    if generated_at:
        return "ready"
    if error_reason:
        return "failed"
    return "generating"


def is_quota_error(message) -> bool:
    m = (message or "").lower()
    return any(k in m for k in _QUOTA_MARKERS)


def failure_reason(exc) -> str:
    """A concise real reason for the founder/admin/logs (NOT shown to the coach).
    Capped so a giant provider payload can't bloat the row."""
    s = str(exc).strip()
    return (s[:500] if s else exc.__class__.__name__)


def dead_letter_reason(existing_error_reason, generated_at, reason):
    """What error_reason to write when a report job is dead-lettered (given up after
    repeated failures). Returns the value to set, or None to leave the report as-is:
      * already generated -> None (a success beat the dead-letter; don't fail it)
      * already has a reason (handle() set it) -> keep that specific reason
      * otherwise -> the given reason, or a generic 'gave up' message
    This is the tail case where the worker died before handle() could record why."""
    if generated_at:
        return None
    if existing_error_reason:
        return existing_error_reason
    return reason or "This report could not be generated after several attempts."
