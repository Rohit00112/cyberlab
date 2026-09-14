"""Research platform schemas (Phase 6, PRD §70-§72)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DatasetKind = Literal[
    "submissions",
    "skill_profiles",
    "badges",
    "hints",
    "labs",
    "learning_progress",
    "engagements",
    "all",
]


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: DatasetKind
    description: str | None = Field(default=None, max_length=2000)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


class ResearchDatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    kind: str
    pseudonymized: bool
    row_count: int
    file_ref: str | None
    created_by: uuid.UUID | None
    expires_at: datetime | None
    created_at: datetime


class MetricsLearning(BaseModel):
    assessed_users: int
    completion_rate: float
    avg_skill_delta: float
    retention_rate: float
    median_days_to_competency: float | None


class MetricsEngagement(BaseModel):
    weekly_active_users: int
    challenges_attempted: int
    hints_used: int
    median_return_days: float | None


class ChallengeQualityMetric(BaseModel):
    challenge_id: uuid.UUID
    slug: str
    title: str
    success_rate: float
    median_solve_seconds: float | None
    abandonment_rate: float


class MetricsRecommendations(BaseModel):
    served: int
    accepted: int
    solved: int
    acceptance_rate: float
    completion_rate: float


class ResearchMetricsOut(BaseModel):
    learning: MetricsLearning
    engagement: MetricsEngagement
    challenge_quality: list[ChallengeQualityMetric]
    recommendations: MetricsRecommendations
    generated_at: datetime


GraphNodeType = Literal["skill", "challenge", "category"]
GraphRelation = Literal["requires", "in", "co_solved", "co_required", "step"]


class GraphNode(BaseModel):
    id: str
    type: GraphNodeType
    label: str
    meta: dict = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: GraphRelation
    weight: float


class ResearchGraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    generated_at: datetime


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    model_ref: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    params: dict | None = None


class ExperimentUpdate(BaseModel):
    status: str | None = Field(default=None, max_length=16)
    metrics: dict | None = None


class ResearchExperimentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    model_ref: str
    params: dict | None
    metrics: dict | None
    status: str
    created_by: uuid.UUID | None
    created_at: datetime