"""Skill profile schema."""
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class SkillProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    skill_id: uuid.UUID
    skill_slug: str
    skill_name: str
    competency_level: float
    last_updated: datetime
