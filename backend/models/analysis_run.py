import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import Base

# Event columns snapshotted into an archive so a superseded run can be restored
# verbatim. id/created_at/game_id/organization_id are set fresh on restore.
ARCHIVE_EVENT_COLUMNS = (
    "event_type", "side", "time_seconds", "down", "distance", "field_position",
    "hash_position", "formation", "play_type", "defensive_front", "coverage",
    "blitz", "result", "yards_gained", "personnel", "motion", "player",
    "is_highlight", "coach_note", "extra_data",
)


class AnalysisRunArchive(Base):
    """A preserved snapshot of one superseded AI-detection run.

    A coach pays for every run and may want several takes (a cheap Quick Test,
    then a Deep pass). Re-running analysis must NEVER silently lose the prior
    run's plays. Instead of hard-deleting the previous auto-detected events, the
    detector snapshots them here (one row per superseded run, plays stored as
    JSON) before writing the new run. The active game keeps showing just the
    current run so every report stays correct, while every prior take stays
    recoverable until the coach explicitly deletes it.
    """

    __tablename__ = "analysis_run_archives"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    # Human label shown in the Play Log's "Previous runs" list.
    label = Column(String)
    play_count = Column(Integer, nullable=False, default=0)
    # Serialized Event rows (every column) so a run can be restored verbatim.
    plays = Column(JSONB, nullable=False, default=list)
    archived_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
