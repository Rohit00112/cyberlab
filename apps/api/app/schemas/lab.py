"""Lab schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class LabOut(BaseModel):
    id: uuid.UUID
    challenge_id: uuid.UUID
    challenge_title: str | None = None
    challenge_slug: str | None = None
    status: str
    connection_hint: str | None = None
    network_name: str | None = None
    container_name: str | None = None
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None
    job_id: uuid.UUID | None = None
    time_remaining_seconds: int | None = None


class LabExtendIn(BaseModel):
    additional_minutes: int = 30


class LabAdminOut(LabOut):
    user_id: uuid.UUID | None = None
    user_display_name: str | None = None
    user_email: str | None = None


class LabListOut(BaseModel):
    items: list[LabAdminOut]
    total: int
    offset: int
    limit: int