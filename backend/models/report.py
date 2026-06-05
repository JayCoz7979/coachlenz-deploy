import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, LargeBinary
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from .base import Base

class TendencyReport(Base):
    __tablename__ = "tendency_reports"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"))
    game_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    sport = Column(String, nullable=False)
    report_type = Column(String, nullable=False, default="opponent")
    title = Column(String, nullable=False)
    summary_json = Column(LargeBinary)
    prose_sections = Column(JSONB, default=list)
    is_trial = Column(Boolean, nullable=False, default=False)
    watermarked = Column(Boolean, nullable=False, default=False)
    generated_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
