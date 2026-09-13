"""Audit log query helpers (PRD §51 security telemetry)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_logs import AuditLog
from app.models.users import User
from app.schemas.audit import AuditLogOut


async def list_audit_logs(
    db: AsyncSession,
    *,
    event: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLogOut], int]:
    conditions = [AuditLog.event == event] if event else []
    total = int(
        await db.scalar(select(func.count()).select_from(AuditLog).where(*conditions)) or 0
    )
    rows = (
        await db.execute(
            select(AuditLog, User.display_name)
            .outerjoin(User, User.id == AuditLog.user_id)
            .where(*conditions)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [
        AuditLogOut(
            id=log.id,
            event=log.event,
            user_id=log.user_id,
            display_name=display_name,
            target_id=log.target_id,
            ip_address=log.ip_address,
            details=log.details,
            created_at=log.created_at,
        )
        for log, display_name in rows
    ], total