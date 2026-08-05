from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from backend.models.base import get_db
from backend.models.user import User
from backend.models.comms import ClipAssignment
from backend.models.clip import Clip
from backend.services.auth import get_current_user

router = APIRouter(prefix="/assignments", tags=["assignments"])

class AssignmentCreate(BaseModel):
    clip_id: str
    assigned_to: str
    note: Optional[str] = None
    due_date: Optional[str] = None

@router.get("")
async def list_assignments(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ClipAssignment).where(ClipAssignment.organization_id == user.organization_id).order_by(ClipAssignment.created_at.desc()))
    assignments = result.scalars().all()
    return [{"id": str(a.id), "clip_id": str(a.clip_id), "assigned_to": str(a.assigned_to) if a.assigned_to else None, "note": a.note, "completed_at": a.completed_at.isoformat() if a.completed_at else None} for a in assignments]

@router.post("")
async def create_assignment(body: AssignmentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Verify the clip and the assignee both belong to the caller's org, so a user
    # can't assign a clip they don't own or hand work to someone outside their org.
    clip = await db.execute(select(Clip.id).where(
        Clip.id == body.clip_id, Clip.organization_id == user.organization_id))
    if not clip.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Clip not found")
    assignee = await db.execute(select(User.id).where(
        User.id == body.assigned_to, User.organization_id == user.organization_id))
    if not assignee.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="That person isn't in your organization.")
    assignment = ClipAssignment(organization_id=user.organization_id, assigned_by=user.id, **body.dict())
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return {"id": str(assignment.id)}

@router.post("/{assignment_id}/complete")
async def complete_assignment(assignment_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(update(ClipAssignment).where(ClipAssignment.id == assignment_id, ClipAssignment.organization_id == user.organization_id).values(completed_at=datetime.utcnow()))
    await db.commit()
    return {"ok": True}
