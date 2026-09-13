"""User-facing and sysadmin user-management endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.db.session import get_db
from app.schemas.users import AdminUserOut, AdminUserUpdate, UserProfile
from app.services.users import get_profile, list_users, update_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserProfile)
async def my_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
) -> UserProfile:
    """Personal profile: identity, join date, stats, recent solves."""
    return await get_profile(db, user.id, roles=user.roles)


@router.get("", response_model=list[AdminUserOut])
async def get_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("user.view"))],
    role: str | None = Query(default=None, max_length=64),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[AdminUserOut]:
    """Sysadmin user directory with aggregate stats (PRD §41)."""
    rows, _total = await list_users(db, role=role, q=q, limit=limit, offset=offset)
    return rows


@router.patch("/{user_id}", response_model=AdminUserOut)
async def update_user_endpoint(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_permission("user.manage"))],
) -> AdminUserOut:
    """Suspend/activate a user or adjust roles (PRD §41, audited)."""
    updated = await update_user(
        db,
        user_id=user_id,
        is_active=payload.is_active,
        roles=payload.roles,
        request=request,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return updated
