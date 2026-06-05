import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import Base

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="member")
    phone = Column(String)
    phone_verified = Column(Boolean, nullable=False, default=False)
    email_verified = Column(Boolean, nullable=False, default=False)
    avatar_url = Column(String)
    is_active = Column(Boolean, nullable=False, default=True)
    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="users")
