import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class AnalysisUsage(Base):
    """One row per analysis run, attributed to the coach who triggered it. Powers the
    Athletic Dept usage dashboard (usage by coach / sport / type) and per-coach caps."""
    __tablename__ = "analysis_usage"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    sport = Column(String)
    analysis_type = Column(String)   # fast | deep | deep_grade
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CoachUsageLimit(Base):
    """An AD-set monthly analysis cap for one coach. Absent row = unlimited."""
    __tablename__ = "coach_usage_limits"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_coach_usage_limit"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    monthly_run_limit = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
