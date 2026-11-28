import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class LeadMagnetLead(Base):
    """A visitor who traded name + a validated email (phone optional) for a free
    download, e.g. the printable Halftime Sheet PDF (source='halftime_pdf').

    Public, unauthenticated intake, so no organization. One row per (lower(email),
    source); a repeat submission refreshes it. The phone is stored only because the
    visitor volunteered it. CoachLenz never texts it (no SMS anywhere)."""
    __tablename__ = "lead_magnet_leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String, nullable=False, default="halftime_pdf")
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String)
    consent_email = Column(Boolean, nullable=False, default=False)
    consent_text = Column(Text)
    # Opaque token in the download link shown after submit.
    download_token = Column(String, nullable=False)
    ip_address = Column(String)
    user_agent = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
