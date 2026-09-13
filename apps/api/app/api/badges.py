"""Badge endpoints (Phase 4, PRD §34)."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.db.session import get_db
from app.models.badges import Badge
from app.schemas.badge import BadgeCreate, BadgeEarned, BadgeOut, BadgeUpdate
from app.services import badges as badge_service

router = APIRouter(tags=["badges"])


@router.get("/badges", response_model=list[BadgeOut])
async def list_badges(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Public badge catalogue."""
    return await badge_service.list_badges(db)


@router.get("/badges/me", response_model=list[BadgeEarned])
async def my_badges(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("badge.view"))],
):
    return await badge_service.earned_badges(db, user.id)


@router.get("/admin/badges", response_model=list[BadgeOut])
async def admin_list_badges(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("badge.manage"))],
):
    return await badge_service.list_badges(db, include_inactive=True)


@router.post("/admin/badges", response_model=BadgeOut, status_code=status.HTTP_201_CREATED)
async def create_badge(
    data: BadgeCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("badge.manage"))],
):
    return await badge_service.create_badge(db, data, user.id, request=request)


@router.patch("/admin/badges/{badge_id}", response_model=BadgeOut)
async def update_badge(
    badge_id: uuid.UUID,
    data: BadgeUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("badge.manage"))],
):
    badge = await db.get(Badge, badge_id)
    if badge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Badge not found")
    return await badge_service.update_badge(db, badge, data, user.id, request=request)


@router.delete("/admin/badges/{badge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_badge(
    badge_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("badge.manage"))],
):
    badge = await db.get(Badge, badge_id)
    if badge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Badge not found")
    await badge_service.delete_badge(db, badge, user.id, request=request)