import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from .base import Base

class TeamSubmission(Base):
    __tablename__ = "team_submissions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submitter_name = Column(String, nullable=False)
    submitter_email = Column(String, nullable=False)
    team_name = Column(String, nullable=False)
    sport = Column(String, nullable=False)
    school_or_org = Column(String, nullable=False)
    level = Column(String)
    achievement = Column(String, nullable=False)
    season = Column(String)
    month_year = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    votes = Column(Integer, nullable=False, default=0)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("submitter_email", "month_year"),)

class FeaturedTeam(Base):
    __tablename__ = "featured_teams"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = Column(UUID(as_uuid=True), ForeignKey("team_submissions.id"), nullable=False)
    month_year = Column(String, nullable=False, unique=True)
    display_order = Column(Integer, nullable=False, default=0)
    featured_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
