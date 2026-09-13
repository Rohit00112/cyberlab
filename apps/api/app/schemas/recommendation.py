"""Adaptive recommendation schemas."""
from __future__ import annotations

import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.skill import SkillBrief


class ChallengeRecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    challenge_id: uuid.UUID
    slug: str
    title: str
    category: str
    difficulty: str
    points: int
    difficulty_score: float
    recommendation_score: float
    skills: list[SkillBrief] = Field(default_factory=list)
