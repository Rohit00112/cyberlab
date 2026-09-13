"""Competition schemas (Phase 3, PRD §24)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CompetitionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    rules: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    registration_ends_at: datetime | None = None
    allow_teams: bool = False
    max_team_size: int = Field(default=4, ge=1, le=10)
    scoring_mode: Literal["standard", "override"] = "standard"


class CompetitionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    rules: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    registration_ends_at: datetime | None = None
    allow_teams: bool | None = None
    max_team_size: int | None = Field(default=None, ge=1, le=10)
    scoring_mode: Literal["standard", "override"] | None = None


class ChallengeShot(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    category: str
    difficulty: str
    points: int
    environment_type: str


class CompetitionChallengeOut(BaseModel):
    challenge: ChallengeShot
    position: int
    points: int | None = None


class CompetitionSummary(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str | None = None
    status: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    registration_ends_at: datetime | None = None
    allow_teams: bool
    max_team_size: int
    scoring_mode: str
    freeze_leaderboard: bool
    frozen_at: datetime | None = None
    challenge_count: int = 0
    participant_count: int = 0
    created_at: datetime
    updated_at: datetime


class TeamOut(BaseModel):
    id: uuid.UUID
    competition_id: uuid.UUID
    name: str
    role: str
    member_count: int = 1
    members: list[str] = Field(default_factory=list)


class ParticipantSelf(BaseModel):
    registered: bool
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    entity_name: str | None = None
    team: TeamOut | None = None


class CompetitionOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str | None = None
    rules: str | None = None
    status: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    registration_ends_at: datetime | None = None
    allow_teams: bool
    max_team_size: int
    scoring_mode: str
    freeze_leaderboard: bool
    frozen_at: datetime | None = None
    challenge_count: int = 0
    participant_count: int = 0
    team_count: int = 0
    challenges: list[CompetitionChallengeOut] = Field(default_factory=list)
    me: ParticipantSelf | None = None
    created_at: datetime
    updated_at: datetime


class CompetitionChallengeAdd(BaseModel):
    challenge_id: uuid.UUID
    points: int | None = Field(default=None, ge=0)


class CompetitionTransitionIn(BaseModel):
    action: Literal[
        "start_registration",
        "schedule",
        "start",
        "finish",
        "archive",
    ]


class TeamCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class CompetitionLeaderboardOut(BaseModel):
    items: list[CompetitionLeaderboardEntry]


class CompetitionLeaderboardEntry(BaseModel):
    rank: int
    entity_type: str
    entity_id: uuid.UUID
    display_name: str
    points: int
    solved_count: int
    last_solve_at: datetime | None = None