import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class HalftimePdfLead(Base):
    """A coach who asked for the free printable Halftime Sheet PDF on /live-tracker.

    Double opt-in: the row is 'pending' until the coach clicks the single-use,
    24-hour confirmation link; only then is it 'confirmed' and the PDF emailed.
    token_hash is HMAC-SHA256(SECRET_KEY, token); the raw token is never stored.
    phone is optional and is never texted (no SMS anywhere)."""
    __tablename__ = "halftime_pdf_leads"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String)
    source = Column(String, nullable=False, default="halftime_pdf")
    status = Column(String, nullable=False, default="pending")  # pending | confirmed
    consent_text = Column(String, nullable=False)
    consented_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    submit_ip = Column(String)
    token_hash = Column(String)
    token_expires_at = Column(DateTime(timezone=True))
    token_used_at = Column(DateTime(timezone=True))
    confirmation_sent_at = Column(DateTime(timezone=True))
    confirmation_send_count = Column(Integer, nullable=False, default=0)
    confirmed_at = Column(DateTime(timezone=True))
    confirmed_ip = Column(String)
    pdf_sent_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
