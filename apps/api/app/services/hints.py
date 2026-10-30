"""Progressive hint reveal and per-user reveal counts (PRD §22)."""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.rust_engine import reveal_hint_in_rust
from app.models.challenges import Challenge
from app.models.hint_reveals import HintReveal
from app.models.users import User
from app.services.users import record_audit


async def revealed_counts(
    db: AsyncSession, user_id: uuid.UUID, challenge_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Map challenge_id -> number of hints this user has unlocked."""
    if not challenge_ids:
        return {}
    rows = (
        await db.execute(
            select(HintReveal.challenge_id, func.count())
            .where(
                HintReveal.user_id == user_id,
                HintReveal.challenge_id.in_(challenge_ids),
            )
            .group_by(HintReveal.challenge_id)
        )
    ).all()
    return {challenge_id: int(count) for challenge_id, count in rows}


async def reveal_hint(
    db: AsyncSession,
    *,
    user: User,
    challenge: Challenge,
    hint_index: int,
    request=None,
) -> int:
    """Unlock hint ``hint_index`` in order. Returns the new revealed count.

    Progressive: only the next unrevealed hint may be unlocked at a time.
    Re-revealing an already-unlocked hint is a no-op (idempotent).
    """
    if hint_index < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid hint index"
        )

    if get_settings().rust_core_url:
        return await reveal_hint_in_rust(
            str(challenge.id), str(user.id), user.roles,
            request.client.host if request and request.client else None,
            hint_index,
        )

    # Match Rust's per-user, per-challenge advisory transaction lock without
    # requiring an UPDATE privilege on the users table.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"{user.id}:{challenge.id}"},
    )

    total = len(challenge.hints or [])
    existing = (
        await db.scalar(
            select(func.count())
            .select_from(HintReveal)
            .where(
                HintReveal.user_id == user.id,
                HintReveal.challenge_id == challenge.id,
            )
        )
        or 0
    )
    if hint_index >= total:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {total} hints available",
        )

    already = await db.scalar(
        select(HintReveal).where(
            HintReveal.user_id == user.id,
            HintReveal.challenge_id == challenge.id,
            HintReveal.hint_index == hint_index,
        )
    )
    if already is not None:
        # Idempotent no-op: retrying the same reveal changes nothing.
        return existing

    if hint_index != existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Reveal hints in order — hint {existing} next",
        )

    db.add(
        HintReveal(
            user_id=user.id,
            challenge_id=challenge.id,
            hint_index=hint_index,
        )
    )
    try:
        # record_audit commits the session; including the pending HintReveal
        # makes the audit mandatory for a successful unlock.
        await record_audit(
            db,
            event="hint.reveal",
            user_id=user.id,
            target_id=challenge.slug,
            details={"hint_index": hint_index},
            request=request,
        )
    except Exception:
        await db.rollback()
        raise
    return existing + 1
