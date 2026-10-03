import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class PrivacyRequest(Base):
    """A parent/guardian (or eligible student) request to ACCESS or DELETE a
    student-athlete's data, per COPPA/FERPA. Public intake (no login), then an admin
    verifies the requester and fulfills it, which scrubs/deletes the identified data
    and emails a Deletion Certificate. The row is the audit trail (status history +
    resolution + IP + certificate id)."""
    __tablename__ = "privacy_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # 'access' | 'deletion'
    request_type = Column(String, nullable=False)
    requester_name = Column(String, nullable=False)
    requester_email = Column(String, nullable=False)
    # 'parent' | 'guardian' | 'eligible_student' | 'school_official' | 'other'
    relationship = Column(String, nullable=False)
    # Free text the requester provides to identify the data.
    school_or_org = Column(String)
    student_name = Column(String, nullable=False)
    student_details = Column(Text)   # jersey / team / season / grad year notes
    details = Column(Text)           # free-form request detail

    # 'pending' -> 'verified' -> 'completed' | 'rejected'
    status = Column(String, nullable=False, default="pending")
    resolution_note = Column(Text)
    certificate_id = Column(String)  # set when a deletion is completed

    # Org the admin resolved this request to (set at verify/fulfill time).
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"))

    # Opaque token for the public status check (so only the requester, who has the
    # link, can poll their own request).
    status_token = Column(String, nullable=False)
    ip_address = Column(String)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    verified_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
