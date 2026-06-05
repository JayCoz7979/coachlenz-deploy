import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Integer, Date, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import Base

class CoachProfile(Base):
    __tablename__ = "coach_profiles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    name = Column(String, nullable=False)
    sport = Column(String)
    position = Column(String)
    bio = Column(Text)
    photo_url = Column(String)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

class CoachMove(Base):
    __tablename__ = "coach_moves"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coach_id = Column(UUID(as_uuid=True), ForeignKey("coach_profiles.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    school_name = Column(String, nullable=False)
    role = Column(String)
    sport = Column(String)
    start_date = Column(Date)
    end_date = Column(Date)
    is_current = Column(Boolean, nullable=False, default=False)
    wins = Column(Integer)
    losses = Column(Integer)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class AdminPermission(Base):
    __tablename__ = "admin_permissions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    permission = Column(String, nullable=False)
    granted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    granted_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)
    target_type = Column(String)
    target_id = Column(UUID(as_uuid=True))
    details = Column(JSONB, default=dict)
    ip_address = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
