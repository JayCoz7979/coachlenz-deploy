import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class LegalAcceptance(Base):
    """One row per accepted document. `document` is 'terms' | 'privacy' |
    'student_data'; `version` records which text was accepted so a re-acceptance
    can be required when the attorney finalizes/updates it."""
    __tablename__ = "legal_acceptances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    document = Column(String, nullable=False)
    version = Column(String, nullable=False)
    ip_address = Column(String)
    accepted_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
