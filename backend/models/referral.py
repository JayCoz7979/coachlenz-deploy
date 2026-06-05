import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from .base import Base

class ReferralCode(Base):
    __tablename__ = "referral_codes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    code = Column(String, unique=True, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class Referral(Base):
    __tablename__ = "referrals"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    referrer_org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    referred_org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    referral_code_id = Column(UUID(as_uuid=True), ForeignKey("referral_codes.id"))
    status = Column(String, nullable=False, default="pending")
    commission_tier = Column(Integer, nullable=False, default=1)
    commission_pct = Column(Numeric(5, 2), nullable=False, default=10.00)
    stripe_credit_cents = Column(Integer)
    credited_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

class ReferralSettings(Base):
    __tablename__ = "referral_settings"
    id = Column(Integer, primary_key=True, default=1)
    tier1_pct = Column(Numeric(5, 2), nullable=False, default=10.00)
    tier2_pct = Column(Numeric(5, 2), nullable=False, default=15.00)
    tier3_pct = Column(Numeric(5, 2), nullable=False, default=20.00)
    tier1_min_referrals = Column(Integer, nullable=False, default=0)
    tier2_min_referrals = Column(Integer, nullable=False, default=3)
    tier3_min_referrals = Column(Integer, nullable=False, default=10)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
