from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from backend.models.base import get_db
from backend.models.user import User
from backend.models.comms import Thread, ThreadMember, Message
from backend.services.auth import get_current_user

router = APIRouter(prefix="/threads", tags=["threads"])

class ThreadCreate(BaseModel):
    title: Optional[str] = None
    context_type: Optional[str] = None
    context_id: Optional[str] = None

class MessageCreate(BaseModel):
    body: str
    parent_id: Optional[str] = None

@router.get("")
async def list_threads(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Thread).where(Thread.organization_id == user.organization_id).order_by(Thread.updated_at.desc()))
    threads = result.scalars().all()
    return [{"id": str(t.id), "title": t.title, "context_type": t.context_type, "context_id": str(t.context_id) if t.context_id else None} for t in threads]

@router.post("")
async def create_thread(body: ThreadCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    thread = Thread(organization_id=user.organization_id, created_by=user.id, **body.dict())
    db.add(thread)
    await db.flush()
    db.add(ThreadMember(thread_id=thread.id, user_id=user.id))
    await db.commit()
    return {"id": str(thread.id)}

@router.get("/{thread_id}/messages")
async def get_messages(thread_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Thread).where(Thread.id == thread_id, Thread.organization_id == user.organization_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Thread not found")
    msgs = await db.execute(select(Message).where(Message.thread_id == thread_id).order_by(Message.created_at))
    messages = msgs.scalars().all()
    return [{"id": str(m.id), "body": m.body, "author_id": str(m.author_id) if m.author_id else None, "created_at": m.created_at.isoformat()} for m in messages]

@router.post("/{thread_id}/messages")
async def post_message(thread_id: str, body: MessageCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Thread).where(Thread.id == thread_id, Thread.organization_id == user.organization_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Thread not found")
    msg = Message(thread_id=thread_id, organization_id=user.organization_id, author_id=user.id, **body.dict())
    db.add(msg)
    await db.commit()
    return {"id": str(msg.id)}
