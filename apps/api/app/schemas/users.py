"""User profile schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProfileSolve(BaseModel):
    """One correctly solved challenge as shown on the student profile."""

    model_config = ConfigDict(from_attributes=True)

    challenge_id: uuid.UUID
    slug: str
    title: str
    points: int
    skills: list[str] = Field(default_factory=list)
    solved_at: datetime


class UserProfile(BaseModel):
    """Self-serve profile: identity, join date, stats and recent solves."""

    id: uuid.UUID
    email: str | None = None
    display_name: str | None = None
    roles: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    points: int = 0
    solved_count: int = 0
    attempts: int = 0
    recent_solves: list[ProfileSolve] = Field(default_factory=list)


class AdminUserOut(BaseModel):
    """One row of the sysadmin user directory (PRD §41)."""

    id: uuid.UUID
    email: str | None = None
    display_name: str | None = None
    roles: list[str] = Field(default_factory=list)
    is_active: bool = True
    points: int = 0
    solved_count: int = 0
    attempts: int = 0
    created_at: datetime | None = None


class AdminUserUpdate(BaseModel):
    """Sysadmin actions on a user account."""

    is_active: bool | None = None
    roles: list[str] | None = None
