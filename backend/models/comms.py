import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from .base import Base

class Thread(Base):
    __tablename__ = "threads"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    title = Column(String)
    context_type = Column(String)
    context_id = Column(UUID(as_uuid=True))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

class ThreadMember(Base):
    __tablename__ = "thread_members"
    thread_id = Column(UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    joined_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class Message(Base):
    __tablename__ = "messages"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    body = Column(Text, nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"))
    edited_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class MessageMention(Base):
    __tablename__ = "message_mentions"
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)

class ThreadRead(Base):
    __tablename__ = "thread_reads"
    thread_id = Column(UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    last_read_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class Playlist(Base):
    __tablename__ = "playlists"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(String)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    is_shared = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

class PlaylistClip(Base):
    __tablename__ = "playlist_clips"
    playlist_id = Column(UUID(as_uuid=True), ForeignKey("playlists.id", ondelete="CASCADE"), primary_key=True)
    clip_id = Column(UUID(as_uuid=True), ForeignKey("clips.id", ondelete="CASCADE"), primary_key=True)
    position = Column(Integer, nullable=False, default=0)
    note = Column(String)

class ClipAssignment(Base):
    __tablename__ = "clip_assignments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    clip_id = Column(UUID(as_uuid=True), ForeignKey("clips.id", ondelete="CASCADE"), nullable=False)
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    note = Column(String)
    due_date = Column(DateTime)
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class FilmPackage(Base):
    __tablename__ = "film_packages"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    description = Column(String)
    clip_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    share_token = Column(String, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    expires_at = Column(DateTime(timezone=True))
    view_count = Column(Integer, nullable=False, default=0)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    body = Column(String)
    data = Column(JSONB, default=dict)
    read_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
