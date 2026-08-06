from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class FeatureFlag(Base):
    """A runtime override of a feature's env-var default (migration 044). One row
    per toggled feature; absence means 'use the env default'. Toggled from the
    admin control panel; read via services.feature_flags."""
    __tablename__ = "feature_flags"
    key = Column(String, primary_key=True)
    enabled = Column(Boolean, nullable=False)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
