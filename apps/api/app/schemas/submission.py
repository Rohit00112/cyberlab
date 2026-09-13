"""Submission and leaderboard schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FlagSubmit(BaseModel):
    flag: str = Field(min_length=1, max_length=500)


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    challenge_id: uuid.UUID
    is_correct: bool
    earned_points: int
    created_at: datetime


class FlagSubmitResult(BaseModel):
    correct: bool
    points: int
    already_solved: bool = False
    message: str


class ChallengeSubmissionStatus(BaseModel):
    solved: bool = False
    attempts: int = 0
    points: int = 0


class UserStats(BaseModel):
    points: int = 0
    solved_count: int = 0
    attempts: int = 0


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: uuid.UUID
    display_name: str | None = None
    points: int
    solved_count: int


class SubmissionReviewOut(BaseModel):
    """One submission row as seen by faculty (PRD §7.2 analytics)."""

    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str | None = None
    challenge_id: uuid.UUID
    challenge_title: str | None = None
    is_correct: bool
    earned_points: int
    created_at: datetime


class PerChallengeStat(BaseModel):
    challenge_id: uuid.UUID
    slug: str
    title: str
    attempts: int = 0
    solves: int = 0


class AnalyticsSummary(BaseModel):
    total_users: int = 0
    total_submissions: int = 0
    total_solves: int = 0
    success_rate: float = 0.0
    total_points_awarded: int = 0
    top_challenges: list[PerChallengeStat] = []
    top_students: list[LeaderboardEntry] = []
