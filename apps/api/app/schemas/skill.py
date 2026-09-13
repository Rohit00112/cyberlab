"""Skill taxonomy, profiles and analytics schemas (Phase 4, PRD §25-28)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    description: str | None = None
    path: str | None = None
    icon: str | None = None
    is_active: bool = True
    challenge_count: int = 0


class SkillBrief(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    icon: str | None = None


class SkillCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    parent_id: uuid.UUID | None = None
    icon: str | None = Field(default=None, max_length=32)
    is_active: bool = True


class SkillUpdate(BaseModel):
    slug: str | None = Field(default=None, min_length=2, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    parent_id: uuid.UUID | None = None
    icon: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None


class SkillEvidence(BaseModel):
    challenge_id: uuid.UUID
    challenge_title: str
    difficulty: str
    earned_points: int
    solved_at: datetime


class SkillScore(BaseModel):
    skill: SkillBrief
    score: int = 0
    solved_count: int = 0
    total_points: int = 0
    evidence: list[SkillEvidence] = Field(default_factory=list)


class SkillProfileOut(BaseModel):
    user_id: uuid.UUID
    display_name: str | None = None
    total_points: int = 0
    solved_count: int = 0
    skills: list[SkillScore] = Field(default_factory=list)


class SkillAggregate(BaseModel):
    skill: SkillBrief
    students_with_evidence: int = 0
    total_solves: int = 0
    total_points: int = 0
    avg_score: float = 0.0


class ChallengeDifficultyOut(BaseModel):
    challenge_id: uuid.UUID
    slug: str
    title: str
    estimated_minutes: int | None = None
    attempts: int = 0
    distinct_students: int = 0
    solvers: int = 0
    success_rate: float = 0.0
    median_seconds: float | None = None
    avg_attempts_per_student: float = 0.0
    hint_users: int = 0
    hint_usage: float = 0.0
    verdict: str = "insufficient_data"


class ChallengeAttemptOut(BaseModel):
    challenge_id: uuid.UUID
    slug: str
    title: str
    category: str
    points: int
    solved: bool = False
    attempts: int = 0
    earned_points: int = 0
    hints_revealed: int = 0
    first_attempt_at: datetime | None = None
    solved_at: datetime | None = None


class StudentAnalyticsOut(BaseModel):
    user_id: uuid.UUID
    display_name: str | None = None
    email: str | None = None
    total_points: int = 0
    solved_count: int = 0
    attempts: int = 0
    hint_reveals: int = 0
    badges: list[dict] = Field(default_factory=list)
    challenges: list[ChallengeAttemptOut] = Field(default_factory=list)
    skills: list[SkillScore] = Field(default_factory=list)