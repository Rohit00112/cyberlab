"""Audit log models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: uuid.UUID
    event: str
    user_id: uuid.UUID | None = None
    display_name: str | None = None
    target_id: str | None = None
    ip_address: str | None = None
    details: dict[str, Any] | None = None
    created_at: datetime