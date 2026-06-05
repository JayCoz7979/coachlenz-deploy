from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from backend.models.base import get_db
from backend.models.user import User
from backend.models.comms import Notification
from backend.services.auth import get_current_user
from datetime import datetime

router = APIRouter(prefix="/notifications", tags=["notifications"])

@router.get("")
async def list_notifications(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(50))
    notifs = result.scalars().all()
    return [{"id": str(n.id), "type": n.type, "title": n.title, "body": n.body, "data": n.data, "read_at": n.read_at.isoformat() if n.read_at else None, "created_at": n.created_at.isoformat()} for n in notifs]

@router.post("/{notif_id}/read")
async def mark_read(notif_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(update(Notification).where(Notification.id == notif_id, Notification.user_id == user.id).values(read_at=datetime.utcnow()))
    await db.commit()
    return {"ok": True}

@router.post("/read-all")
async def mark_all_read(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at == None).values(read_at=datetime.utcnow()))
    await db.commit()
    return {"ok": True}
