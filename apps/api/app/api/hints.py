"""Progressive hint reveal endpoints (PRD §22).

Reveals are progressive and per-user; each unlock imposes the configured
``hint_penalty`` so ``earned = points - hint_penalty * revealed`` (PRD §21).
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.api.ratelimit import rate_limit
from app.db.session import get_db
from app.models.challenges import Challenge
from app.services import hints as hint_service

router = APIRouter(tags=["hints"])


async def _get_published(db: AsyncSession, challenge_id: uuid.UUID) -> Challenge:
    challenge = await db.get(Challenge, challenge_id)
    if challenge is None or not challenge.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found"
        )
    return challenge


@router.post(
    "/challenges/{challenge_id}/hints/{hint_index}/reveal",
    status_code=status.HTTP_201_CREATED,
)
async def reveal_hint(
    challenge_id: uuid.UUID,
    hint_index: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.attempt"))],
    _limit: Annotated[None, Depends(rate_limit("hints.reveal", limit=20, window_seconds=60))],
):
    """Unlock the next unrevealed hint in order (PRD §22)."""
    challenge = await _get_published(db, challenge_id)
    revealed = await hint_service.reveal_hint(
        db,
        user=user,
        challenge=challenge,
        hint_index=hint_index,
        request=request,
    )
    return {"challenge_id": str(challenge.id), "hints_revealed": revealed}