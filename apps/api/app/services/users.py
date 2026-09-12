"""User synchronization and audit helpers."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_logs import AuditLog
from app.models.users import User


async def sync_user(db: AsyncSession, claims: dict) -> User:
    """Upsert a local users row keyed by the Keycloak subject identifier."""
    sub = claims["sub"]
    user = await db.scalar(select(User).where(User.keycloak_sub == sub))

    email = claims.get("email")
    name = claims.get("name") or claims.get("preferred_username")

    if user is None:
        user = User(keycloak_sub=sub, email=email, display_name=name)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    changed = False
    if email and user.email != email:
        user.email = email
        changed = True
    if name and user.display_name != name:
        user.display_name = name
        changed = True
    if changed:
        await db.commit()
    return user


async def record_audit(
    db: AsyncSession,
    event: str,
    user_id: uuid.UUID | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    ip = request.client.host if request and request.client else None
    db.add(
        AuditLog(
            event=event,
            user_id=user_id,
            target_id=target_id,
            ip_address=ip,
            details=details,
        )
    )
    await db.commit()