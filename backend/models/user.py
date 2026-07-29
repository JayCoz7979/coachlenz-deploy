import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import Base

# Every role value the users.role column may hold. This is the SINGLE SOURCE for the
# users_role_check DB constraint (migration 028 must match this list) AND declares the
# constraint on the model so the SQLite integration test enforces it too — closing the
# model/migration drift that let an invalid role reach production. Keep in sync with
# services.permissions.ROLE_PERMISSIONS (guarded by test_role_constraint).
ALLOWED_USER_ROLES = frozenset({
    # legacy
    "owner", "admin", "coach", "member",
    # scouting + coaching staff (RBAC)
    "analyst", "reviewer", "coordinator", "head_coach",
    "coordinator_offense", "coordinator_defense", "coordinator_special_teams",
    "position_coach", "athletic_trainer",
})
_ROLE_CHECK_SQL = "role IN (" + ", ".join(f"'{r}'" for r in sorted(ALLOWED_USER_ROLES)) + ")"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_ROLE_CHECK_SQL, name="users_role_check"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="member")
    phone = Column(String)
    phone_verified = Column(Boolean, nullable=False, default=False)
    email_verified = Column(Boolean, nullable=False, default=False)
    avatar_url = Column(String)
    is_active = Column(Boolean, nullable=False, default=True)
    # Bumped on logout / password change / password reset to revoke all previously
    # issued refresh tokens (they embed this value; /auth/refresh checks it).
    token_version = Column(Integer, nullable=False, default=0, server_default="0")
    last_login_at = Column(DateTime(timezone=True))
    # Single-use password-reset token (SHA-256 hash of the emailed token) + expiry.
    reset_token_hash = Column(String)
    reset_token_expires = Column(DateTime(timezone=True))
    # Email verification code (SHA-256 hash of a 6-digit code) + expiry. Phone
    # verification is handled by Twilio Verify (no code stored locally).
    email_verify_code_hash = Column(String)
    email_verify_expires = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="users")
