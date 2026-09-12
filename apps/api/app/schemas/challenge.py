"""Challenge request/response schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.flags import CATEGORIES, DIFFICULTIES, STATUSES


class AuthorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str | None = None


class ChallengeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    instructions: str | None = None
    category: str = Field(min_length=2, max_length=32)
    difficulty: str = Field(min_length=2, max_length=16)
    points: int = Field(default=0, ge=0)
    estimated_minutes: int | None = Field(default=None, ge=1)
    skills: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
    flag: str | None = None
    flag_format: str | None = Field(default=None, max_length=120)
    environment_type: str = Field(default="none", max_length=32)
    status: str = Field(default="draft")

    def validate_enums(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"invalid category: {self.category}")
        if self.difficulty not in DIFFICULTIES:
            raise ValueError(f"invalid difficulty: {self.difficulty}")
        if self.status not in STATUSES:
            raise ValueError(f"invalid status: {self.status}")


class ChallengeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1)
    instructions: str | None = None
    category: str | None = Field(default=None, min_length=2, max_length=32)
    difficulty: str | None = Field(default=None, min_length=2, max_length=16)
    points: int | None = Field(default=None, ge=0)
    estimated_minutes: int | None = Field(default=None, ge=1)
    skills: list[str] | None = None
    prerequisites: list[str] | None = None
    hints: list[str] | None = None
    flag: str | None = None
    flag_format: str | None = Field(default=None, max_length=120)
    environment_type: str | None = Field(default=None, max_length=32)
    status: str | None = None


class ChallengeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    description: str
    instructions: str | None = None
    category: str
    difficulty: str
    points: int
    estimated_minutes: int | None = None
    skills: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
    flag_format: str | None = None
    environment_type: str
    author: AuthorOut | None = None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime