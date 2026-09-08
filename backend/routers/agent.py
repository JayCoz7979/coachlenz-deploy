"""
Operator agent endpoint. Admin-gated (it can read platform-wide gates). The agent is
read-only, so it never changes data, sends anything, or spends money. UATP: the
response carries the agent's identity, the tools it could use, and the full action log.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.base import get_db
from backend.models.user import User
from backend.models.organization import Organization
from backend.services.auth import require_admin, get_current_org
from backend.agent.loop import run_agent

router = APIRouter(prefix="/agent", tags=["agent"])


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
