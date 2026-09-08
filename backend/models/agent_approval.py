import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import Base


class AgentApproval(Base):
    """A mutating action the agent proposed, held for human approval before it runs."""
    __tablename__ = "agent_approvals"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    action = Column(String, nullable=False)
    args = Column(JSONB, nullable=False, default=dict)
    status = Column(String, nullable=False, default="pending")   # pending|approved|rejected|executed
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    decided_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    result = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    decided_at = Column(DateTime(timezone=True))
