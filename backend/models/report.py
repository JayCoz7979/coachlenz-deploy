import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, LargeBinary, Integer
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
    # Optional per-report generation parameters (migration 037). The Live Game
    # halftime report stores {"event_filter": {"max_quarter": 2}} (or {"max_half": 1}
    # for basketball) so the worker scopes the report to first-half plays only.
    # NULL for every scout/film report — the worker treats absence as "no filter".
    params = Column(JSONB)
    is_trial = Column(Boolean, nullable=False, default=False)
    watermarked = Column(Boolean, nullable=False, default=False)
    # Read-only public share link. Null until a coach enables sharing; the token is
    # the capability and share_expires_at gates it (7-day default, 30-day max).
    share_token = Column(String, unique=True)
    share_expires_at = Column(DateTime(timezone=True))
    share_view_count = Column(Integer, nullable=False, default=0, server_default="0")
    generated_at = Column(DateTime(timezone=True))
    # Set when generation errors (Anthropic usage limit, API error, crash). Real
    # reason for founder/admin/logs; the coach sees only a generic message. failed =
    # error_reason set AND generated_at null; cleared on a successful (re)generation.
    error_reason = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
