import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from .base import Base

class Tag(Base):
    __tablename__ = "tags"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    color = Column(String, default="#6366f1")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("organization_id", "name"),)
