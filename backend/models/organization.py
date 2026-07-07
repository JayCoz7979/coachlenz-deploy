import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from .base import Base

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    subscription_tier = Column(String, nullable=False, default="trial")
    is_trial = Column(Boolean, nullable=False, default=True)
    trial_ends_at = Column(DateTime(timezone=True))
    trial_games_used = Column(Integer, nullable=False, default=0)
    stripe_customer_id = Column(String, unique=True)
    stripe_subscription_id = Column(String, unique=True)
    stripe_subscription_status = Column(String)
    has_coach_tenure_access = Column(Boolean, nullable=False, default=False)
    admin_level = Column(String)
    # Sport entitlement lock (set during onboarding, enforced everywhere film is
    # analyzed). Empty list = not yet locked. See backend/services/sports.py.
    chosen_sports = Column(JSONB, nullable=False, default=list)
    onboarding_completed = Column(Boolean, nullable=False, default=False)
    referral_code = Column(String, unique=True)
    referred_by_org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    teams = relationship("Team", back_populates="organization", cascade="all, delete-orphan")
