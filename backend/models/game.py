import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Integer, BigInteger, Float, Date, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import Base

class Game(Base):
    __tablename__ = "games"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"))
    title = Column(String, nullable=False)
    sport = Column(String, nullable=False)
    opponent = Column(String)
    game_date = Column(Date)
    is_home = Column(Boolean)
    # On-field appearance so the vision agent can attribute plays to the right team.
    scout_jersey = Column(String)      # the team being scouted, e.g. "white jerseys, navy helmets"
    opponent_jersey = Column(String)   # the opponent, e.g. "red jerseys"
    r2_key = Column(String)
    r2_url = Column(String)
    r2_expires_at = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer)
    file_size_bytes = Column(BigInteger)
    film_width = Column(Integer)       # ingested video resolution (see migration 021);
    film_height = Column(Integer)      # < 720 height = low-res, jersey reading is limited
    status = Column(String, nullable=False, default="pending")
    error_message = Column(String)
    is_trial_game = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    team = relationship("Team", back_populates="games")
    clips = relationship("Clip", back_populates="game", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="game", cascade="all, delete-orphan")
