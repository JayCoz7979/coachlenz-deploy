from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.base import get_db
from backend.models.user import User
from backend.models.job import Job
from backend.services.auth import get_current_user

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.get("")
async def list_jobs(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).where(Job.organization_id == user.organization_id).order_by(Job.created_at.desc()).limit(50))
    jobs = result.scalars().all()
    return [{"id": str(j.id), "job_type": j.job_type, "status": j.status, "created_at": j.created_at.isoformat(), "error_message": j.error_message} for j in jobs]

@router.get("/{job_id}")
async def get_job(job_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException
    result = await db.execute(select(Job).where(Job.id == job_id, Job.organization_id == user.organization_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"id": str(job.id), "job_type": job.job_type, "status": job.status, "result": job.result, "error_message": job.error_message}
