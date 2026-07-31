import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Boolean, Float, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class CoachLabelCorrection(Base):
    """One label field a coach changed on a play (Engine §14). The raw learning
    signal — org-scoped, CASCADE-deleted with the account."""
    __tablename__ = "coach_label_corrections"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"))
    game_id = Column(UUID(as_uuid=True))
    sport = Column(String, nullable=False)
    field = Column(String, nullable=False)
    category = Column(String)
    old_value = Column(Text)
    new_value = Column(Text)
    was_auto_detected = Column(Boolean, nullable=False, default=False)
    ai_confidence = Column(Float)
    signal = Column(String, nullable=False)   # 'high' | 'low' | 'reclass'
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class AccountLearningAdjustment(Base):
    """A per-account relabel distilled from systematic corrections. Coach accepts
    (status='active') or rejects it; an active adjustment normalizes matching plays
    in that account's future reports."""
    __tablename__ = "account_learning_adjustments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    sport = Column(String, nullable=False)
    field = Column(String, nullable=False)
    from_value = Column(Text, nullable=False)
    to_value = Column(Text, nullable=False)
    support_count = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="pending")   # pending | active | rejected
    note = Column(Text)
    activated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class LabelQualityScore(Base):
    """Rolling per-account label-quality counters (one row per org)."""
    __tablename__ = "label_quality_scores"
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    total_corrections = Column(Integer, nullable=False, default=0)
    high_count = Column(Integer, nullable=False, default=0)
    low_count = Column(Integer, nullable=False, default=0)
    reclass_count = Column(Integer, nullable=False, default=0)
    systematic_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
