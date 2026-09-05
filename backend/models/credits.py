import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class OrgCredits(Base):
    """An org's analysis-credit balance. `included` is granted by the plan and resets
    each month; `purchased` comes from top-up packs and rolls over. Presence of the
    row means the org is on the credit system (see routers/ai_detect.py)."""
    __tablename__ = "org_credits"
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    included = Column(Integer, nullable=False, default=0)
    purchased = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class CreditLedger(Base):
    """Append-only audit of every credit movement (grant, purchase, spend, refund)."""
    __tablename__ = "credit_ledger"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String, nullable=False)            # grant | trial_grant | purchase | spend | refund
    amount = Column(Integer, nullable=False)          # signed total
    included_delta = Column(Integer, nullable=False, default=0)
    purchased_delta = Column(Integer, nullable=False, default=0)
    ref = Column(String)                              # job id, or stripe invoice/session id
    note = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
