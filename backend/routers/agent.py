"""
Operator agent endpoint. Admin-gated (it can read platform-wide gates). The agent is
read-only, so it never changes data, sends anything, or spends money. UATP: the
response carries the agent's identity, the tools it could use, and the full action log.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.models.agent_approval import AgentApproval
from backend.services.auth import require_admin, get_current_org
from backend.agent.loop import run_agent
from backend.agent import workflows

router = APIRouter(prefix="/agent", tags=["agent"])

# Mutating actions the agent may PROPOSE, executed only after a human approves. Each
# maps to a safe, reversible change. Add here (with an executor) rather than giving the
# read-only tool registry write access.
_APPROVABLE = {"set_learning_loop_mode"}


class AgentRun(BaseModel):
    message: str
    dry_run: bool = False


@router.get("/tools")
async def list_tools(user: User = Depends(require_admin)):
    """Discoverable tool list (name + description + schema) for agents and operators."""
    from backend.agent import tools as toolkit
    return {"agent": "CoachLenz Operator",
            "tools": toolkit.anthropic_schema(toolkit.tools_for(is_admin=True))}


@router.post("/run")
async def run(body: AgentRun, user: User = Depends(require_admin),
              org: Organization = Depends(get_current_org), db: AsyncSession = Depends(get_db)):
    return await run_agent(
        db, body.message, is_admin=True,
        organization_id=str(org.id), user_id=str(user.id), dry_run=body.dry_run,
    )


@router.post("/workflow/account-health")
async def account_health(user: User = Depends(require_admin),
                         org: Organization = Depends(get_current_org),
                         db: AsyncSession = Depends(get_db)):
    """Orchestration: chain retention -> conversion -> credit economics into a
    schema-validated account-health verdict."""
    return await workflows.account_health(db, str(org.id))


# ── Mutating actions behind a human-approval gate ───────────────────────────────
class LearningModeRequest(BaseModel):
    manual: bool


@router.post("/actions/learning-mode")
async def request_learning_mode(body: LearningModeRequest,
                                user: User = Depends(require_admin),
                                org: Organization = Depends(get_current_org),
                                db: AsyncSession = Depends(get_db)):
    """Propose a change to the org's learning-loop mode. Queued for human approval,
    NOT applied here."""
    appr = AgentApproval(organization_id=org.id, action="set_learning_loop_mode",
                         args={"manual": bool(body.manual)}, requested_by=user.id)
    db.add(appr)
    await db.commit()
    await db.refresh(appr)
    return {"status": "pending_approval", "approval_id": str(appr.id),
            "action": appr.action, "args": appr.args}


@router.get("/approvals")
async def list_approvals(user: User = Depends(require_admin),
                         org: Organization = Depends(get_current_org),
                         db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(AgentApproval).where(AgentApproval.organization_id == org.id,
                                    AgentApproval.status == "pending")
        .order_by(AgentApproval.created_at.desc())
    )).scalars().all()
    return {"pending": [{"id": str(a.id), "action": a.action, "args": a.args,
                         "created_at": a.created_at.isoformat()} for a in rows]}


async def _execute(db: AsyncSession, appr: AgentApproval) -> str:
    """Apply an approved action. Safe, reversible changes only."""
    if appr.action == "set_learning_loop_mode":
        manual = bool((appr.args or {}).get("manual"))
        await db.execute(update(Organization).where(Organization.id == appr.organization_id)
                         .values(learning_loop_manual=manual))
        return f"learning_loop_manual set to {manual}"
    return "unknown action, nothing done"


@router.post("/approvals/{approval_id}/approve")
async def approve(approval_id: str, user: User = Depends(require_admin),
                  org: Organization = Depends(get_current_org),
                  db: AsyncSession = Depends(get_db)):
    """The human gate: approve a queued action, which then executes."""
    appr = (await db.execute(select(AgentApproval).where(
        AgentApproval.id == approval_id, AgentApproval.organization_id == org.id))).scalar_one_or_none()
    if not appr:
        raise HTTPException(status_code=404, detail="Approval not found")
    if appr.status != "pending":
        raise HTTPException(status_code=409, detail=f"Already {appr.status}")
    result = await _execute(db, appr)
    appr.status = "executed"
    appr.decided_by = user.id
    appr.decided_at = datetime.utcnow()
    appr.result = result
    await db.commit()
    return {"status": "executed", "result": result}


@router.post("/approvals/{approval_id}/reject")
async def reject(approval_id: str, user: User = Depends(require_admin),
                 org: Organization = Depends(get_current_org),
                 db: AsyncSession = Depends(get_db)):
    appr = (await db.execute(select(AgentApproval).where(
        AgentApproval.id == approval_id, AgentApproval.organization_id == org.id))).scalar_one_or_none()
    if not appr:
        raise HTTPException(status_code=404, detail="Approval not found")
    if appr.status != "pending":
        raise HTTPException(status_code=409, detail=f"Already {appr.status}")
    appr.status = "rejected"
    appr.decided_by = user.id
    appr.decided_at = datetime.utcnow()
    await db.commit()
    return {"status": "rejected"}
