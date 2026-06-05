import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import Base

class SurveyPrompt(Base):
    __tablename__ = "survey_prompts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question = Column(String, nullable=False)
    response_type = Column(String, nullable=False, default="text")
    options = Column(JSONB, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    display_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class SurveyResponse(Base):
    __tablename__ = "survey_responses"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    prompt_id = Column(UUID(as_uuid=True), ForeignKey("survey_prompts.id"), nullable=False)
    response_text = Column(String)
    response_rating = Column(Integer)
    response_choice = Column(String)
    submitted_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
