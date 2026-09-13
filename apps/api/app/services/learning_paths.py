"""Learning path service and progress tracking."""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.challenges import Challenge
from app.models.learning_paths import LearningPath, LearningPathStep
from app.models.submissions import Submission
from app.schemas.learning_path import LearningPathCreate, LearningPathDetail, LearningPathStepOut, LearningPathSummary


async def list_published_paths(db: AsyncSession) -> list[LearningPathSummary]:
    rows = (
        await db.scalars(
            select(LearningPath).where(LearningPath.is_published.is_(True)).order_by(LearningPath.title.asc())
        )
    ).all()
    return [LearningPathSummary.model_validate(p) for p in rows]


async def create_learning_path(db: AsyncSession, data: LearningPathCreate) -> LearningPathSummary:
    slug = data.slug.strip().lower().replace(" ", "-")
    existing = await db.scalar(select(LearningPath).where(LearningPath.slug == slug))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A learning path with this slug exists")

    path = LearningPath(
        slug=slug,
        title=data.title.strip(),
        description=data.description,
        is_published=data.is_published,
    )
    db.add(path)
    await db.commit()
    await db.refresh(path)
    return LearningPathSummary.model_validate(path)


async def add_step(
    db: AsyncSession, path_id: uuid.UUID, challenge_id: uuid.UUID, step_order: int
) -> None:
    path = await db.get(LearningPath, path_id)
    if not path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Path not found")

    challenge = await db.get(Challenge, challenge_id)
    if not challenge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")

    step = LearningPathStep(
        learning_path_id=path.id,
        challenge_id=challenge.id,
        step_order=step_order,
    )
    db.add(step)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Challenge already in path"
        )


async def get_path_with_progress(
    db: AsyncSession, path_id: uuid.UUID, user_id: uuid.UUID | None
) -> LearningPathDetail:
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Path not found")

    steps_rows = (
        await db.execute(
            select(LearningPathStep.challenge_id, LearningPathStep.step_order, Challenge.title)
            .join(Challenge, Challenge.id == LearningPathStep.challenge_id)
            .where(LearningPathStep.learning_path_id == path.id)
            .order_by(LearningPathStep.step_order.asc())
        )
    ).all()

    solved_set = set()
    if user_id is not None:
        solved_ids = (
            await db.scalars(
                select(Submission.challenge_id)
                .where(Submission.user_id == user_id, Submission.is_correct.is_(True))
            )
        ).all()
        solved_set = set(solved_ids)

    out_steps = []
    unlocked_found = False

    for challenge_id, step_order, title in steps_rows:
        if challenge_id in solved_set:
            step_status = "completed"
        elif not unlocked_found:
            step_status = "unlocked"
            unlocked_found = True
        else:
            step_status = "locked"

        out_steps.append(
            LearningPathStepOut(
                challenge_id=challenge_id,
                title=title,
                step_order=step_order,
                status=step_status,
            )
        )

    return LearningPathDetail(
        id=path.id,
        slug=path.slug,
        title=path.title,
        description=path.description,
        is_published=path.is_published,
        steps=out_steps,
    )
