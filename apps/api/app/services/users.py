"""User synchronization, profiles and audit helpers."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_logs import AuditLog
from app.models.challenges import Challenge
from app.models.submissions import Submission
from app.models.users import User
from app.schemas.users import ProfileSolve, UserProfile


async def sync_user(db: AsyncSession, claims: dict) -> User:
    """Upsert a local users row keyed by the Keycloak subject identifier."""
    sub = claims["sub"]
    user = await db.scalar(select(User).where(User.keycloak_sub == sub))

    email = claims.get("email")
    name = claims.get("name") or claims.get("preferred_username")

    if user is None:
        user = User(keycloak_sub=sub, email=email, display_name=name)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    changed = False
    if email and user.email != email:
        user.email = email
        changed = True
    if name and user.display_name != name:
        user.display_name = name
        changed = True
    if changed:
        await db.commit()
    return user


async def get_profile(db: AsyncSession, user_id: uuid.UUID, *, roles: list[str]) -> UserProfile:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(Submission.earned_points), 0),
                func.count().filter(Submission.is_correct),
                func.count(),
            ).where(Submission.user_id == user_id)
        )
    ).one()
    points, solved_count, attempts = row

    solves = (
        await db.execute(
            select(
                Submission.challenge_id,
                Challenge.slug,
                Challenge.title,
                Challenge.points,
                Challenge.skills,
                Submission.created_at,
            )
            .join(Challenge, Challenge.id == Submission.challenge_id)
            .where(
                Submission.user_id == user_id,
                Submission.is_correct.is_(True),
            )
            .order_by(Submission.created_at.desc())
            .limit(10)
        )
    ).all()

    recent_solves = [
        ProfileSolve(
            challenge_id=challenge_id,
            slug=slug,
            title=title,
            points=points,
            skills=list(skills or []),
            solved_at=created_at,
        )
        for challenge_id, slug, title, points, skills, created_at in solves
    ]

    return UserProfile(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        roles=roles,
        created_at=user.created_at,
        points=int(points),
        solved_count=int(solved_count),
        attempts=int(attempts),
        recent_solves=recent_solves,
    )


async def record_audit(
    db: AsyncSession,
    event: str,
    user_id: uuid.UUID | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    ip = request.client.host if request and request.client else None
    db.add(
        AuditLog(
            event=event,
            user_id=user_id,
            target_id=target_id,
            ip_address=ip,
            details=details,
        )
    )
    await db.commit()