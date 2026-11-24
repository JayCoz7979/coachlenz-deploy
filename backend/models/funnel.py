import uuid
from datetime import datetime
from sqlalchemy import Boolean, Column, String, DateTime, ForeignKey
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
    source = Column(String)                   # channel: utm_source | referrer host | 'direct'
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
    # Waitlist context (migration 057). Null on older email-only rows.
    first_name = Column(String)
    school = Column(String)
    sport = Column(String)
    role = Column(String)
    role_branch = Column(String)
    is_adult = Column(Boolean)
    consent_text_version = Column(String)
    lead_magnet = Column(String)
    utm_source = Column(String)
    utm_medium = Column(String)
    utm_campaign = Column(String)
    utm_content = Column(String)
    utm_term = Column(String)
    referrer = Column(String)
    landing_path = Column(String)
    ref_code = Column(String)
    confirm_token_hash = Column(String)
    confirm_sent_at = Column(DateTime(timezone=True))
    confirmed_at = Column(DateTime(timezone=True))
    unsubscribed_at = Column(DateTime(timezone=True))
    unsubscribe_token = Column(String)
    resend_contact_id = Column(String)
    has_account = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
