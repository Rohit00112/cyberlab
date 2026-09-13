"""Challenge catalogue endpoints (RBAC-scoped, see PRD §13/§54)."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.core.flags import STATUSES
from app.db.session import get_db
from app.models.challenges import Challenge
from app.schemas.challenge import ChallengeCreate, ChallengeOut, ChallengeUpdate
from app.services import challenges as service

router = APIRouter(prefix="/challenges", tags=["challenges"])


async def _get_editable(db: AsyncSession, challenge_id: uuid.UUID) -> Challenge:
    challenge = await db.get(Challenge, challenge_id)
    if challenge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    return challenge


@router.get("", response_model=list[ChallengeOut])
async def list_challenges(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
    category: str | None = Query(default=None, max_length=32),
    difficulty: str | None = Query(default=None, max_length=16),
    status_filter: str | None = Query(
        default=None, alias="status", pattern="^(" + "|".join(STATUSES) + ")$"
    ),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    challenges, _ = await service.list_challenges(
        db,
        user.roles,
        user_id=user.id,
        category=category,
        difficulty=difficulty,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return challenges


@router.get("/{challenge_id}", response_model=ChallengeOut)
async def get_challenge(
    challenge_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
):
    return await service.get_challenge(
        db, challenge_id, user.roles, user_id=user.id
    )


@router.post("", response_model=ChallengeOut, status_code=status.HTTP_201_CREATED)
async def create_challenge(
    payload: ChallengeCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.create"))],
):
    try:
        payload.validate_enums()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
    return await service.create_challenge(db, payload, user.id, request=request)


@router.patch("/{challenge_id}", response_model=ChallengeOut)
async def update_challenge(
    challenge_id: uuid.UUID,
    payload: ChallengeUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.edit"))],
):
    challenge = await _get_editable(db, challenge_id)
    return await service.update_challenge(db, challenge, payload, user.id, request=request)


@router.post("/{challenge_id}/publish", response_model=ChallengeOut)
async def publish_challenge(
    challenge_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.publish"))],
):
    challenge = await _get_editable(db, challenge_id)
    return await service.publish_challenge(db, challenge, user.id, request=request)


@router.delete("/{challenge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_challenge(
    challenge_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.edit"))],
):
    challenge = await _get_editable(db, challenge_id)
    await service.delete_challenge(db, challenge, user.id, request=request)