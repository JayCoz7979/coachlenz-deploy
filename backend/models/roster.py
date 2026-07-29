import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import Base


class RosterPlayer(Base):
    """A named player on a team's roster, keyed to a jersey number. The team carries
    the season + sport, so a roster is season-scoped through its team. The unique
    (team_id, jersey_number) lets EAGLE-EYE jersey reads resolve to a named player."""
    __tablename__ = "roster_players"
    __table_args__ = (
        UniqueConstraint("team_id", "jersey_number", name="uq_roster_team_jersey"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    jersey_number = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String)
    position = Column(String)
    grade_year = Column(String)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    team = relationship("Team")
