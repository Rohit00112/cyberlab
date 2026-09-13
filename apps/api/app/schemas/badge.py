"""Badge schemas (Phase 4, PRD §34)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BadgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    criteria: dict
    icon: str | None = None
    skill_id: uuid.UUID | None = None
    skill_name: str | None = None
    is_active: bool = True


class BadgeCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    criteria: dict = Field(default_factory=dict)
    icon: str | None = Field(default=None, max_length=32)
    skill_id: uuid.UUID | None = None
    is_active: bool = True


class BadgeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    criteria: dict | None = None
    icon: str | None = Field(default=None, max_length=32)
    skill_id: uuid.UUID | None = None
    is_active: bool | None = None


class BadgeEarned(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    icon: str | None = None
    skill_name: str | None = None
    earned_at: datetime
    evidence: dict | None = None


class BadgeGrantResult(BaseModel):
    granted: list[str] = Field(default_factory=list)
    already_earned: list[str] = Field(default_factory=list)