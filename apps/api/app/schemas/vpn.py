"""WireGuard VPN Pydantic schemas (Phase 5)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class VPNPeerOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    public_key: str
    allocated_ip: str
    is_active: bool
    allowed_subnets: list[str] | None = None
    expires_at: datetime | None = None
    created_at: datetime


class VPNConfigOut(BaseModel):
    config_text: str
    allocated_ip: str
    server_endpoint: str
    server_public_key: str
    allowed_ips: str
    dns: str | None = None


class VPNPeerRegisterIn(BaseModel):
    client_public_key: str | None = None
