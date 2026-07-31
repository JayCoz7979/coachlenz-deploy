"""
Report-scoped AI Coach Chat (Engine §13).

Endpoints (all under an owned, generated report):
  GET  /reports/{report_id}/chat   -> the chat thread for this report
  POST /reports/{report_id}/chat   -> ask a question, get a grounded answer

Isolation: every query filters organization_id == the caller's org (app-layer
isolation, matching the rest of the platform). A report the org doesn't own 404s,
so no cross-account film, tendency data, or chat history is ever reachable.

Cost: chat is included in the report — no separate charge (§13). We never touch
the billing/usage path here.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.report import TendencyReport
from backend.models.report_chat import ReportChatMessage
from backend.models.event import Event
from backend.services.auth import get_current_user, get_current_org
from backend.services.encryption import decrypt_json
from backend.services.agent_log import log_agent_action
from backend.services import report_chat as chat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["report-chat"])

# A question longer than this is almost certainly a paste / abuse, not a coach's
# film question. Reject early rather than pay to tokenize it.
_MAX_QUESTION_CHARS = 1000


class ChatAsk(BaseModel):
    question: str


async def _load_owned_report(report_id: str, org_id, db: AsyncSession) -> TendencyReport:
    result = await db.execute(select(TendencyReport).where(
        TendencyReport.id == report_id,
        TendencyReport.organization_id == org_id,
    ))
    report = result.scalar_one_or_none()
    if not report:
        # 404 (not 403) — don't confirm the report exists to a non-owner.
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def _serialize(m: ReportChatMessage) -> dict:
    return {
        "id": str(m.id),
        "role": m.role,
        "content": m.content,
        "confidence": m.confidence,
        "answered": m.answered,
        "cutups": m.cutups or [],
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@router.get("/{report_id}/chat")
async def get_chat(report_id: str,
                   user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    """The full chat thread for a report the caller's org owns (oldest first)."""
    await _load_owned_report(report_id, user.organization_id, db)
    result = await db.execute(
        select(ReportChatMessage)
        .where(
            ReportChatMessage.report_id == report_id,
            ReportChatMessage.organization_id == user.organization_id,  # defense in depth
        )
        .order_by(ReportChatMessage.created_at.asc())
    )
    return {"messages": [_serialize(m) for m in result.scalars().all()]}


@router.post("/{report_id}/chat")
async def ask_chat(report_id: str, body: ChatAsk,
                   user: User = Depends(get_current_user),
                   org: Organization = Depends(get_current_org),
                   db: AsyncSession = Depends(get_db)):
    """Ask the Film Assistant a question about this report. Answers come only from
    the report's film; an ungrounded question returns the canonical 'upload another
    game' line. Persists both the question and the answer, logs UATP."""
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="Ask a question about the report.")
    if len(question) > _MAX_QUESTION_CHARS:
        raise HTTPException(status_code=422, detail="That question is too long. Keep it short.")

    report = await _load_owned_report(report_id, user.organization_id, db)
    if not report.generated_at:
        # Can't chat a report that hasn't finished (or that failed) — nothing to ground on.
        raise HTTPException(status_code=409, detail="This report is still generating. Try again once it's ready.")

    # Decrypt the tendency/heat data (best-effort; the written sections carry the report either way).
    summary = None
    if report.summary_json:
        try:
            summary = decrypt_json(report.summary_json)
        except Exception:
            summary = None

    # This report's tagged plays (org-scoped, defense in depth) -> video cutups.
    events = []
    if report.game_ids:
        ev = await db.execute(
            select(Event).where(
                Event.game_id.in_(report.game_ids),
                Event.organization_id == user.organization_id,
                Event.event_type != "scout_meta",
            ).order_by(Event.game_id, Event.time_seconds.asc())
        )
        events = ev.scalars().all()

    cutups = chat.build_cutups(events)
    context = chat.build_report_context(report, summary, cutups)

    # Prior turns for continuity (org-scoped).
    hist_rows = (await db.execute(
        select(ReportChatMessage)
        .where(
            ReportChatMessage.report_id == report_id,
            ReportChatMessage.organization_id == user.organization_id,
        )
        .order_by(ReportChatMessage.created_at.asc())
    )).scalars().all()
    history = chat.to_messages(hist_rows)

    try:
        answer = await chat.answer_question(
            report_context=context, cutups=cutups, history=history, question=question,
        )
    except Exception as e:
        logger.error(f"[report_chat] {report_id} answer failed: {e}")
        raise HTTPException(status_code=502, detail="The film assistant is unavailable right now. Try again in a moment.")

    # Persist the question and the answer together.
    user_row = ReportChatMessage(
        organization_id=org.id, report_id=report.id, user_id=user.id,
        role="user", content=question,
    )
    assistant_row = ReportChatMessage(
        organization_id=org.id, report_id=report.id, user_id=None,
        role="assistant", content=answer["content"],
        confidence=answer["confidence"], answered=answer["answered"],
        cutups=answer["cutups"], total_cost_usd=answer["cost_usd"],
    )
    db.add(user_row)
    db.add(assistant_row)
    await db.commit()

    # UATP: identity + reason + confidence + cost, and a gap flag on an ungrounded
    # question. Best-effort; never blocks the response.
    if not answer["answered"]:
        level, reason = "warn", f"Film gap: no coverage for '{question[:120]}'"
    elif answer["needs_review"]:
        level, reason = "escalation", f"Low-confidence answer ({chat.band(answer['confidence'])}); flagged for review"
    else:
        level, reason = "success", f"Answered report question ({chat.band(answer['confidence'])} confidence)"
    await log_agent_action(
        action="report_chat_answer",
        organization_id=str(org.id),
        phase="chat",
        reason=reason,
        confidence=answer["confidence"],
        level=level,
        agent_name=chat.AGENT_NAME,
        agent_role=chat.AGENT_ROLE,
        detail={
            "report_id": str(report.id),
            "answered": answer["answered"],
            "needs_review": answer["needs_review"],
            "cutups": len(answer["cutups"]),
            "total_cost_usd": f"{answer['cost_usd']:.6f}",
        },
    )

    return {
        "answer": _serialize(assistant_row),
        "needs_review": answer["needs_review"],
    }
