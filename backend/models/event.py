import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Integer, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from .base import Base

class Event(Base):
    __tablename__ = "events"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    clip_id = Column(UUID(as_uuid=True), ForeignKey("clips.id"))
    event_type = Column(String, nullable=False)
    time_seconds = Column(Float)
    down = Column(Integer)
    distance = Column(Integer)
    field_position = Column(String)
    hash_position = Column(String)
    formation = Column(String)
    play_type = Column(String)
    result = Column(String)
    yards_gained = Column(Integer)
    personnel = Column(String)
    motion = Column(Boolean, default=False)
    extra_data = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    game = relationship("Game", back_populates="events")
