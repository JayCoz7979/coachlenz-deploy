"""Append-only waitlist consent log and the suppression list.

Rows in marketing_consent_events are never updated or deleted by application
code. email_suppressions keeps a sha256 of a lowercased address after a lead
row is gone.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class MarketingConsentEvent(Base):
    __tablename__ = "marketing_consent_events"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True))
    event_type = Column(String, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    email = Column(String, nullable=False)
    consent_text = Column(Text)
    consent_version = Column(String)
    consent_text_sha256 = Column(String)
    page_url = Column(String)
    form_id = Column(String)
    utm_source = Column(String)
    utm_medium = Column(String)
    utm_campaign = Column(String)
    utm_content = Column(String)
    utm_term = Column(String)
    referrer = Column(String)
    role = Column(String)
    ip_address = Column(String)
    user_agent = Column(String)
    doi_sent_at = Column(DateTime(timezone=True))
    doi_confirmed_at = Column(DateTime(timezone=True))
    unsubscribe_method = Column(String)
    resend_message_id = Column(String)


class EmailSuppression(Base):
    __tablename__ = "email_suppressions"
    email_sha256 = Column(String, primary_key=True)
    suppressed_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    reason = Column(String, nullable=False)
