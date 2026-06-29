"""
UATP (Universal Agent Transparency Protocol) logging service.

Every CGE agent must log its decisions with a reason and a confidence score.
This module is the single write path for that log. Logging must NEVER crash the
agent it is observing — every write is best-effort and swallows its own errors
(failure transparency must not itself be a failure mode).
"""
import logging
from typing import Optional, Any

from backend.models.base import AsyncSessionLocal
from backend.models.agent_log import AgentLog

logger = logging.getLogger(__name__)

# ── Agent identity (UATP identity disclosure) ──────────────────────────────
AGENT_NAME = "Film Assistant"
AGENT_ROLE = "your AI film assistant"

# ── Confidence policy (UATP confidence flagging + escalation) ──────────────
# Below HARD_FLOOR: the read is discarded outright (handled in the worker).
# Between HARD_FLOOR and ESCALATION_THRESHOLD: the play is persisted but flagged
#   needs_review=True and an escalation is logged — the agent does NOT present a
#   low-confidence read as fact; it hands it to a human to verify.
# At or above ESCALATION_THRESHOLD: treated as a confident read.
HARD_FLOOR = 0.5
ESCALATION_THRESHOLD = 0.65

VALID_LEVELS = ("info", "success", "warn", "escalation", "error")


def confidence_band(score: Optional[float]) -> str:
    if score is None:
        return "unknown"
    if score >= 0.8:
        return "high"
    if score >= ESCALATION_THRESHOLD:
        return "medium"
    return "low"


async def log_agent_action(
    *,
    action: str,
    game_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    job_id: Optional[str] = None,
    phase: Optional[str] = None,
    reason: Optional[str] = None,
    confidence: Optional[float] = None,
    level: str = "info",
    detail: Optional[dict] = None,
    agent_name: str = AGENT_NAME,
    agent_role: str = AGENT_ROLE,
) -> None:
    """Persist one UATP action-log row. Best-effort: never raises."""
    if level not in VALID_LEVELS:
        level = "info"
    try:
        async with AsyncSessionLocal() as db:
            db.add(AgentLog(
                organization_id=organization_id,
                game_id=game_id,
                job_id=job_id,
                agent_name=agent_name,
                agent_role=agent_role,
                phase=phase,
                action=action,
                reason=reason,
                confidence=confidence,
                level=level,
                detail=detail or {},
            ))
            await db.commit()
    except Exception as e:  # logging must not break the agent
        logger.error(f"[uatp] failed to write agent log ({action}): {e}")
