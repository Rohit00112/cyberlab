"""Submission endpoints: flag validation, personal progress, and leaderboard."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.db.session import get_db
from app.models.challenges import Challenge
from app.schemas.submission import (
    AnalyticsSummary,
    ChallengeSubmissionStatus,
    FlagSubmit,
    FlagSubmitResult,
    SubmissionOut,
    SubmissionReviewOut,
    UserStats,
)
from app.services import challenges as challenge_service
from app.services import submissions as submission_service

router = APIRouter(tags=["submissions"])


async def _get_published(db: AsyncSession, challenge_id: uuid.UUID) -> Challenge:
    challenge = await db.get(Challenge, challenge_id)
    if challenge is None or not challenge.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found"
        )
    return challenge


@router.post(
    "/challenges/{challenge_id}/submissions",
    response_model=FlagSubmitResult,
    status_code=status.HTTP_201_CREATED,
)
async def submit_flag(
    challenge_id: uuid.UUID,
    payload: FlagSubmit,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("submission.create"))],
):
    challenge = await _get_published(db, challenge_id)
    result = await submission_service.submit_flag(
        db,
        user_id=user.id,
        challenge=challenge,
        flag=payload.flag,
        can_edit=challenge_service.can_edit(user.roles),
        request=request,
    )
    return result


@router.get("/submissions/me", response_model=list[SubmissionOut])
async def my_submissions(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
    limit: int = Query(default=20, ge=1, le=100),
):
    return await submission_service.my_submissions(db, user.id, limit=limit)


@router.get("/submissions/status", response_model=dict[str, ChallengeSubmissionStatus])
async def my_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
):
    return await submission_service.submission_status_map(db, user.id)


@router.get("/submissions/stats", response_model=UserStats)
async def my_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
):
    return await submission_service.user_stats(db, user.id)

@router.get("/submissions/review", response_model=list[SubmissionReviewOut])
async def review_submissions(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("submission.review"))],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """All student flag submissions, newest first (PRD §7.2)."""
    rows, _total = await submission_service.review_submissions(
        db, limit=limit, offset=offset
    )
    return rows


@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("analytics.view"))],
):
    """Platform-wide analytics (PRD §7.2, §50)."""
    return await submission_service.analytics_summary(db)
