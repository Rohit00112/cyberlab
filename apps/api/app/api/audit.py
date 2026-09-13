"""Audit log review endpoints (PRD §51 security telemetry)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.db.session import get_db
from app.schemas.audit import AuditLogOut
from app.services import audit as audit_service

router = APIRouter(tags=["audit"])


@router.get("/audit/logs", response_model=list[AuditLogOut])
async def audit_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("audit.view"))],
    event: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Security-relevant events, newest first (PRD §54 Security - audit logs)."""
    rows, _total = await audit_service.list_audit_logs(
        db, event=event, limit=limit, offset=offset
    )
    return rows