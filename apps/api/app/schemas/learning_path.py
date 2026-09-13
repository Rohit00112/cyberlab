"""Learning path schemas."""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LearningPathStepCreate(BaseModel):
    challenge_id: uuid.UUID
    step_order: int


class LearningPathCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    is_published: bool = False


class LearningPathStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    challenge_id: uuid.UUID
    title: str
    step_order: int
    status: Literal["completed", "unlocked", "locked"]


class LearningPathSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    description: str | None = None
    is_published: bool


class LearningPathDetail(LearningPathSummary):
    steps: list[LearningPathStepOut] = Field(default_factory=list)
