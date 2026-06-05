import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import Base

class Clip(Base):
    __tablename__ = "clips"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    title = Column(String)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    r2_key = Column(String)
    r2_url = Column(String)
    r2_expires_at = Column(DateTime(timezone=True))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    game = relationship("Game", back_populates="clips")
