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