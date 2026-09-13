"""User-facing endpoints: self-serve profile (admin management added separately)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.db.session import get_db
from app.schemas.users import UserProfile
from app.services.users import get_profile

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserProfile)
async def my_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
) -> UserProfile:
    """Personal profile: identity, join date, stats, recent solves."""
    return await get_profile(db, user.id, roles=user.roles)
