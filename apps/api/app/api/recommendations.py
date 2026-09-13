"""API router for challenge recommendations."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.db.session import get_db
from app.schemas.recommendation import ChallengeRecommendationOut
from app.services import recommendations as rec_service

router = APIRouter(tags=["recommendations"])

@router.get("/recommendations/challenges", response_model=list[ChallengeRecommendationOut])
async def get_challenge_recommendations(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
    limit: int = 10,
):
    return await rec_service.get_recommendations(db, user.id, limit)
