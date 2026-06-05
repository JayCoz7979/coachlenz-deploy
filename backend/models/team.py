import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import Base

class Team(Base):
    __tablename__ = "teams"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    sport = Column(String, nullable=False)
    level = Column(String)
    season = Column(String)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="teams")
    games = relationship("Game", back_populates="team")
