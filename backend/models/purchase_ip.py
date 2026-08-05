import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class PurchaseIPLog(Base):
    """One row per checkout attempt — the client IP + user agent at the moment a
    coach initiated a purchase. Evidence for chargeback / dispute responses."""
    __tablename__ = "purchase_ip_log"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True))
    ip = Column(String)
    user_agent = Column(String)
    tier = Column(String)
    stripe_session_id = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
