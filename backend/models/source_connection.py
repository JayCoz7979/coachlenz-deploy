import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, LargeBinary, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class SourceConnection(Base):
    """A coach/org's stored login for an external film source (e.g. Hudl).

    Credentials are encrypted at rest (Fernet) and only decrypted inside the
    ingest worker to authenticate a headless capture session.
    """
    __tablename__ = "source_connections"
    __table_args__ = (UniqueConstraint("organization_id", "provider", name="uq_org_provider"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String, nullable=False)  # 'hudl' | 'nfhs'
    account_email = Column(String)             # shown to the user (not secret)
    encrypted_credentials = Column(LargeBinary, nullable=False)
    status = Column(String, nullable=False, default="connected")  # connected | error
    last_error = Column(String)
    last_verified_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
