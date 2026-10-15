"""Pydantic schemas for machine templates and versions (Phase 3)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MachineTemplateBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    description: str = ""
    category: str = "general"
    difficulty: str = "intermediate"
    os_type: str = "linux"  # linux | windows | freebsd | custom
    architecture: str = "x86_64"  # x86_64 | arm64
    base_image: str = Field(..., min_length=1, max_length=512)
    services: list[dict[str, Any]] | None = None
    challenge_modules: list[dict[str, Any]] | None = None
    resource_spec: dict[str, Any] | None = None  # cpu, memory_mb, disk_gb
    network_policy: dict[str, Any] | None = None
    exposure_policy: str = "vpn_only"
    flag_definitions: list[dict[str, Any]] | None = None
    hint_config: list[dict[str, Any]] | None = None
    max_lease_minutes: int = 120
    estimated_minutes: int | None = None
    tags: list[str] | None = None
    prerequisites: list[str] | None = None


class MachineTemplateCreate(MachineTemplateBase):
    slug: str = Field(..., min_length=2, max_length=120)


class MachineTemplateUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    difficulty: str | None = None
    os_type: str | None = None
    architecture: str | None = None
    base_image: str | None = None
    services: list[dict[str, Any]] | None = None
    challenge_modules: list[dict[str, Any]] | None = None
    resource_spec: dict[str, Any] | None = None
    network_policy: dict[str, Any] | None = None
    exposure_policy: str | None = None
    flag_definitions: list[dict[str, Any]] | None = None
    hint_config: list[dict[str, Any]] | None = None
    max_lease_minutes: int | None = None
    estimated_minutes: int | None = None
    tags: list[str] | None = None
    prerequisites: list[str] | None = None
    status: str | None = None


class MachineTemplateOut(MachineTemplateBase):
    id: uuid.UUID
    slug: str
    status: str
    author_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    version_count: int = 0
    latest_version: int | None = None


class MachineTemplateVersionCreate(BaseModel):
    image_ref: str | None = None
    config_overrides: dict[str, Any] | None = None


class MachineTemplateVersionOut(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID
    version: int
    config_snapshot: dict[str, Any]
    image_ref: str | None = None
    image_hash: str | None = None
    build_log: str | None = None
    status: str
    validation_result: dict[str, Any] | None = None
    validated_at: datetime | None = None
    published_at: datetime | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime


class MachineTemplateValidationResult(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict)


class MachineTemplateApprovalIn(BaseModel):
    action: str  # submit_review | approve | publish | archive
    review_notes: str | None = None
