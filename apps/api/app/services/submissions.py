"""Flag submission, scoring and leaderboard logic (PRD §19-21, §23)."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.flags import verify_flag
from app.models.challenges import Challenge
from app.models.submissions import Submission
from app.models.users import User
from app.schemas.submission import (
    ChallengeSubmissionStatus,
    FlagSubmitResult,
    LeaderboardEntry,
    SubmissionOut,
    UserStats,
)
from app.services.users import record_audit


async def submit_flag(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    challenge: Challenge,
    flag: str,
    can_edit: bool,
    request: Any = None,
) -> FlagSubmitResult:
    if not can_edit and not challenge.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found"
        )
    if challenge.flag_hash is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This challenge has no flag configured",
        )

    correct = verify_flag(flag, challenge.flag_hash)

    if correct:
        existing = await db.scalar(
            select(Submission).where(
                Submission.challenge_id == challenge.id,
                Submission.user_id == user_id,
                Submission.is_correct.is_(True),
            )
        )
        if existing is not None:
            await record_audit(
                db,
                event="submission.attempt",
                user_id=user_id,
                target_id=challenge.slug,
                details={"correct": True, "already_solved": True},
                request=request,
            )
            return FlagSubmitResult(
                correct=True, points=0, already_solved=True, message="Already solved"
            )

    submission = Submission(
        challenge_id=challenge.id,
        user_id=user_id,
        is_correct=correct,
        earned_points=challenge.points if correct else 0,
    )
    db.add(submission)
    try:
        await db.commit()
    except IntegrityError:
        # Concurrent double-solve: the partial unique index already has a row.
        await db.rollback()
        await record_audit(
            db,
            event="submission.attempt",
            user_id=user_id,
            target_id=challenge.slug,
            details={"correct": True, "already_solved": True},
            request=request,
        )
        return FlagSubmitResult(
            correct=True, points=0, already_solved=True, message="Already solved"
        )

    await record_audit(
        db,
        event="submission.solve" if correct else "submission.attempt",
        user_id=user_id,
        target_id=challenge.slug,
        details={"correct": correct, "points": submission.earned_points},
        request=request,
    )

    if correct:
        return FlagSubmitResult(
            correct=True, points=submission.earned_points, message="Correct flag!"
        )
    return FlagSubmitResult(correct=False, points=0, message="Incorrect flag")


async def my_submissions(
    db: AsyncSession, user_id: uuid.UUID, *, limit: int = 20
) -> list[SubmissionOut]:
    rows = (
        await db.scalars(
            select(Submission)
            .where(Submission.user_id == user_id)
            .order_by(Submission.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [SubmissionOut.model_validate(r) for r in rows]


async def submission_status_map(
    db: AsyncSession, user_id: uuid.UUID
) -> dict[str, ChallengeSubmissionStatus]:
    rows = (
        await db.execute(
            select(
                Submission.challenge_id,
                func.count(),
                func.bool_or(Submission.is_correct),
                func.coalesce(func.max(Submission.earned_points), 0),
            )
            .where(Submission.user_id == user_id)
            .group_by(Submission.challenge_id)
        )
    ).all()
    return {
        str(challenge_id): ChallengeSubmissionStatus(
            solved=bool(solved),
            attempts=int(attempts),
            points=int(points),
        )
        for challenge_id, attempts, solved, points in rows
    }


async def user_stats(db: AsyncSession, user_id: uuid.UUID) -> UserStats:
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(Submission.earned_points), 0),
                func.count().filter(Submission.is_correct),
                func.count(),
            ).where(Submission.user_id == user_id)
        )
    ).one()
    points, solved, attempts = row
    return UserStats(points=int(points), solved_count=int(solved), attempts=int(attempts))


async def leaderboard(db: AsyncSession, *, limit: int = 50) -> list[LeaderboardEntry]:
    rows = (
        await db.execute(
            select(
                User.id,
                User.display_name,
                func.coalesce(func.sum(Submission.earned_points), 0),
                func.count().filter(Submission.is_correct),
                func.min(Submission.created_at),
            )
            .join(Submission, Submission.user_id == User.id)
            .where(Submission.is_correct.is_(True))
            .group_by(User.id, User.display_name)
            .order_by(
                func.coalesce(func.sum(Submission.earned_points), 0).desc(),
                func.min(Submission.created_at).asc(),
            )
            .limit(limit)
        )
    ).all()
    return [
        LeaderboardEntry(
            rank=index + 1,
            user_id=user_id,
            display_name=display_name,
            points=int(points),
            solved_count=int(solved),
        )
        for index, (user_id, display_name, points, solved, _first_at) in enumerate(rows)
    ]