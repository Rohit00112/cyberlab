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
from app.models.hint_reveals import HintReveal
from app.models.submissions import Submission
from app.models.users import User
from app.schemas.submission import (
    AnalyticsSummary,
    ChallengeSubmissionStatus,
    FlagSubmitResult,
    LeaderboardEntry,
    PerChallengeStat,
    SubmissionOut,
    SubmissionReviewOut,
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

    if correct:
        revealed = await db.scalar(
            select(func.count())
            .select_from(HintReveal)
            .where(
                HintReveal.user_id == user_id,
                HintReveal.challenge_id == challenge.id,
            )
        ) or 0
        earned = max(challenge.points - (challenge.hint_penalty or 0) * revealed, 0)
    else:
        earned = 0
    submission = Submission(
        challenge_id=challenge.id,
        user_id=user_id,
        is_correct=correct,
        earned_points=earned,
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

async def review_submissions(
    db: AsyncSession, *, limit: int = 50, offset: int = 0
) -> tuple[list[SubmissionReviewOut], int]:
    """Faculty-facing list of all student flag submissions (PRD §7.2)."""
    total = (
        await db.scalar(select(func.count()).select_from(Submission)) or 0
    )
    rows = (
        await db.execute(
            select(
                Submission,
                User.display_name,
                Challenge.title,
            )
            .join(User, User.id == Submission.user_id)
            .join(Challenge, Challenge.id == Submission.challenge_id)
            .order_by(Submission.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [
        SubmissionReviewOut(
            id=submission.id,
            user_id=submission.user_id,
            display_name=display_name,
            challenge_id=submission.challenge_id,
            challenge_title=title,
            is_correct=submission.is_correct,
            earned_points=submission.earned_points,
            created_at=submission.created_at,
        )
        for submission, display_name, title in rows
    ], int(total)


async def analytics_summary(db: AsyncSession) -> AnalyticsSummary:
    """Platform-level analytics for faculty (PRD §7.2, §50)."""
    total_users = int(await db.scalar(select(func.count()).select_from(User)) or 0)
    total_submissions = int(
        await db.scalar(select(func.count()).select_from(Submission)) or 0
    )
    total_solves = int(
        await db.scalar(
            select(func.count())
            .select_from(Submission)
            .where(Submission.is_correct.is_(True))
        )
        or 0
    )
    total_points = int(
        await db.scalar(
            select(func.coalesce(func.sum(Submission.earned_points), 0))
        )
        or 0
    )
    success_rate = round(total_solves / total_submissions, 4) if total_submissions else 0.0

    rows = (
        await db.execute(
            select(
                Challenge.id,
                Challenge.slug,
                Challenge.title,
                func.count(Submission.id),
                func.count().filter(Submission.is_correct),
            )
            .join(Challenge, Challenge.id == Submission.challenge_id)
            .group_by(Challenge.id, Challenge.slug, Challenge.title)
            .order_by(func.count().filter(Submission.is_correct).desc())
            .limit(5)
        )
    ).all()
    top_challenges = [
        PerChallengeStat(
            challenge_id=challenge_id,
            slug=slug,
            title=title,
            attempts=int(attempts),
            solves=int(solves),
        )
        for challenge_id, slug, title, attempts, solves in rows
    ]

    tops = (
        await db.execute(
            select(
                User.id,
                User.display_name,
                func.coalesce(func.sum(Submission.earned_points), 0),
                func.count().filter(Submission.is_correct),
            )
            .join(Submission, Submission.user_id == User.id)
            .where(Submission.is_correct.is_(True))
            .group_by(User.id, User.display_name)
            .order_by(func.coalesce(func.sum(Submission.earned_points), 0).desc())
            .limit(5)
        )
    ).all()
    top_students = [
        LeaderboardEntry(
            rank=index + 1,
            user_id=user_id,
            display_name=display_name,
            points=int(points),
            solved_count=int(solved),
        )
        for index, (user_id, display_name, points, solved) in enumerate(tops)
    ]

    return AnalyticsSummary(
        total_users=total_users,
        total_submissions=total_submissions,
        total_solves=total_solves,
        success_rate=success_rate,
        total_points_awarded=total_points,
        top_challenges=top_challenges,
        top_students=top_students,
    )
