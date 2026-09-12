"""Global leaderboard endpoint (PRD §23)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.db.session import get_db
from app.schemas.submission import LeaderboardEntry
from app.services import submissions as submission_service

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("", response_model=list[LeaderboardEntry])
async def leaderboard(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
    limit: int = Query(default=50, ge=1, le=200),
):
    return await submission_service.leaderboard(db, limit=limit)