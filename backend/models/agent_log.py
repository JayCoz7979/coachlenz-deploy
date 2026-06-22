import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import Base


class AgentLog(Base):
    """UATP action-log row. One per agent decision, with reason and confidence."""
    __tablename__ = "agent_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"))
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"))
    job_id = Column(UUID(as_uuid=True))
    agent_name = Column(String, nullable=False)
    agent_role = Column(String)
    phase = Column(String)
    action = Column(String, nullable=False)
    reason = Column(String)
    confidence = Column(Float)
    level = Column(String, nullable=False, default="info")  # info | success | warn | escalation | error
    detail = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
