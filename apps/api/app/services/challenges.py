"""Challenge CRUD and visibility helpers."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.flags import hash_flag, slugify
from app.core.permissions import has_permission
from app.models.challenges import Challenge
from app.models.users import User
from app.schemas.challenge import AuthorOut, ChallengeCreate, ChallengeOut, ChallengeUpdate
from app.services.hints import revealed_counts
from app.services.skills import sync_challenge_skills
from app.services.users import record_audit


def can_edit(user_roles: list[str]) -> bool:
    return has_permission(user_roles, "challenge.edit") or has_permission(
        user_roles, "challenge.create"
    )


async def list_challenges(
    db: AsyncSession,
    user_roles: list[str],
    *,
    user_id: uuid.UUID | None = None,
    category: str | None = None,
    difficulty: str | None = None,
    status_filter: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[ChallengeOut], int]:
    editor = can_edit(user_roles)

    conditions = []
    if not editor:
        conditions.append(Challenge.status == "published")
    elif status_filter:
        conditions.append(Challenge.status == status_filter)

    if category:
        conditions.append(Challenge.category == category)
    if difficulty:
        conditions.append(Challenge.difficulty == difficulty)

    total = await db.scalar(select(func.count()).select_from(Challenge).where(*conditions))
    challenges = (
        await db.scalars(
            select(Challenge)
            .where(*conditions)
            .order_by(Challenge.points.desc(), Challenge.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    authors = await _authors_map(db)
    counts = await revealed_counts(db, user_id, [c.id for c in challenges]) if user_id else {}
    result = [_to_out(c, authors, editor=editor, revealed_counts=counts) for c in challenges]
    return result, int(total or 0)


async def get_challenge(
    db: AsyncSession,
    challenge_id: uuid.UUID,
    user_roles: list[str],
    *,
    user_id: uuid.UUID | None = None,
) -> ChallengeOut:
    challenge = await db.get(Challenge, challenge_id)
    if challenge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    if not can_edit(user_roles) and not challenge.is_published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    authors = await _authors_map(db)
    counts = await revealed_counts(db, user_id, [challenge.id]) if user_id else {}
    return _to_out(challenge, authors, editor=can_edit(user_roles), revealed_counts=counts)


async def create_challenge(
    db: AsyncSession, data: ChallengeCreate, author_id: uuid.UUID, request: Any = None
) -> ChallengeOut:
    slug = slugify(data.title)
    existing = await db.scalar(select(Challenge).where(Challenge.slug == slug))
    if existing:
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    challenge = Challenge(
        slug=slug,
        title=data.title,
        description=data.description,
        instructions=data.instructions,
        category=data.category,
        difficulty=data.difficulty,
        points=data.points,
        estimated_minutes=data.estimated_minutes,
        skills=data.skills,
        prerequisites=data.prerequisites,
        hints=data.hints,
        flag_hash=hash_flag(data.flag) if data.flag else None,
        flag_format=data.flag_format,
        environment_type=data.environment_type,
        lab_config=data.lab_config,
        author_id=author_id,
        status=data.status,
    )
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)
    await record_audit(
        db, event="challenge.create", user_id=author_id, target_id=challenge.slug, request=request
    )
    await sync_challenge_skills(db, challenge.id, challenge.skills)
    authors = await _authors_map(db)
    return _to_out(challenge, authors)


async def update_challenge(
    db: AsyncSession,
    challenge: Challenge,
    data: ChallengeUpdate,
    user_id: uuid.UUID,
    request: Any = None,
) -> ChallengeOut:
    updates = data.model_dump(exclude_unset=True)
    if "flag" in updates:
        flag = updates.pop("flag")
        if flag is None:
            challenge.flag_hash = None
        else:
            challenge.flag_hash = hash_flag(flag)

    for field, value in updates.items():
        setattr(challenge, field, value)

    challenge.version += 1
    await db.commit()
    await db.refresh(challenge)
    await record_audit(
        db, event="challenge.update", user_id=user_id, target_id=challenge.slug, request=request
    )
    if "skills" in updates:
        await sync_challenge_skills(db, challenge.id, challenge.skills)
    authors = await _authors_map(db)
    return _to_out(challenge, authors)


async def publish_challenge(
    db: AsyncSession, challenge: Challenge, user_id: uuid.UUID, request: Any = None
) -> ChallengeOut:
    if challenge.flag_hash is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A flag is required before publishing",
        )
    challenge.status = "published"
    challenge.version += 1
    await db.commit()
    await db.refresh(challenge)
    await record_audit(
        db, event="challenge.publish", user_id=user_id, target_id=challenge.slug, request=request
    )
    authors = await _authors_map(db)
    return _to_out(challenge, authors)


async def delete_challenge(
    db: AsyncSession, challenge: Challenge, user_id: uuid.UUID, request: Any = None
) -> None:
    slug = challenge.slug
    await db.delete(challenge)
    await db.commit()
    await record_audit(
        db, event="challenge.delete", user_id=user_id, target_id=slug, request=request
    )


async def _authors_map(db: AsyncSession) -> dict[str, Any]:
    rows = (await db.execute(select(User.id, User.display_name))).all()
    return {str(row[0]): row[1] for row in rows}


def _to_out(
    challenge: Challenge,
    authors: dict[str, Any],
    *,
    editor: bool = True,
    revealed_counts: dict[uuid.UUID, int] | None = None,
) -> ChallengeOut:
    if challenge.skills is None:
        challenge.skills = []
    if challenge.prerequisites is None:
        challenge.prerequisites = []
    if challenge.hints is None:
        challenge.hints = []
    all_hints = list(challenge.hints)
    out = ChallengeOut.model_validate(challenge)
    out.hints_count = len(all_hints)
    out.hint_penalty = challenge.hint_penalty or 0
    if editor:
        # Editors manage content and see every hint.
        out.hints = all_hints
        out.hints_revealed = 0
    else:
        revealed = (revealed_counts or {}).get(challenge.id, 0)
        out.hints_revealed = revealed
        out.hints = all_hints[:revealed]
    display = authors.get(str(challenge.author_id))
    out.author = (
        AuthorOut(id=challenge.author_id, display_name=display) if challenge.author_id else None
    )
    return out