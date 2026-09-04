import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import Base


class FunnelEvent(Base):
    """One conversion-funnel event. Anonymous top-of-funnel rows carry a random
    anon_id (localStorage) and no organization; the server-emitted signup steps carry
    the organization once it exists. Platform analytics, read by the founder. No PII."""
    __tablename__ = "funnel_events"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    anon_id = Column(String)
    event = Column(String, nullable=False)   # landing_view|cta_click|signup_view|signup_start|signup_complete
    path = Column(String)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"))
    meta = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class MarketingLead(Base):
    """A visitor who did not sign up but volunteered an email to be nurtured. The
    lower(email) unique index keeps repeat submissions from creating duplicates."""
    __tablename__ = "marketing_leads"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False)
    source = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
