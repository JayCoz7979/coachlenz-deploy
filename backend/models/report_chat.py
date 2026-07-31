import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Boolean, Float, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import Base


class ReportChatMessage(Base):
    """One turn of the report-scoped AI Coach Chat (Engine §13).

    A row is either a coach question (role='user') or a Film Assistant answer
    (role='assistant'). Answers carry UATP fields: confidence, whether the answer
    was grounded in the film (answered), the cited cutups, and the run cost.

    organization_id is the isolation boundary — chat is always scoped to a report
    the org owns; nothing crosses accounts.
    """
    __tablename__ = "report_chat_messages"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    report_id = Column(UUID(as_uuid=True), ForeignKey("tendency_reports.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    role = Column(String, nullable=False)          # 'user' | 'assistant'
    content = Column(Text, nullable=False)
    # Assistant-only UATP columns (null on user rows).
    confidence = Column(Float)                       # 0..1; None = unknown
    answered = Column(Boolean)                       # False => logged as a report gap flag
    cutups = Column(JSONB, nullable=False, default=list)
    total_cost_usd = Column(Numeric(12, 6))          # UATP cost, 6 decimals
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
