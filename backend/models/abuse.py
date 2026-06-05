import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import Base

class DeviceFingerprint(Base):
    __tablename__ = "device_fingerprints"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fingerprint = Column(String, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    ip_address = Column(String)
    user_agent = Column(String)
    first_seen_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    request_count = Column(Integer, nullable=False, default=1)
    is_blocked = Column(Boolean, nullable=False, default=False)

class RiskFlag(Base):
    __tablename__ = "risk_flags"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    flag_type = Column(String, nullable=False)
    severity = Column(String, nullable=False, default="low")
    details = Column(JSONB, default=dict)
    resolved_at = Column(DateTime(timezone=True))
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    action = Column(String, nullable=False)
    resource_type = Column(String)
    resource_id = Column(UUID(as_uuid=True))
    ip_address = Column(String)
    user_agent = Column(String)
    details = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
