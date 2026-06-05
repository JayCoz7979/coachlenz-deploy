import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import Base

class Job(Base):
    __tablename__ = "jobs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"))
    job_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued")
    payload = Column(JSONB, nullable=False, default=dict)
    result = Column(JSONB, default=dict)
    error_message = Column(String)
    attempts = Column(Integer, nullable=False, default=0)
    locked_at = Column(DateTime(timezone=True))
    locked_by = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
