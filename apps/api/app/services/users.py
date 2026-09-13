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
from app.schemas.users import AdminUserOut, ProfileSolve, UserProfile


async def sync_user(db: AsyncSession, claims: dict) -> User:
    """Upsert a local users row keyed by the Keycloak subject identifier."""
    sub = claims["sub"]
    user = await db.scalar(select(User).where(User.keycloak_sub == sub))

    email = claims.get("email")
    name = claims.get("name") or claims.get("preferred_username")
    roles = sorted(claims.get("realm_access", {}).get("roles", []))

    if user is None:
        user = User(keycloak_sub=sub, email=email, display_name=name, roles=roles)
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
    if roles and user.roles != roles:
        user.roles = roles
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


async def list_users(
    db: AsyncSession,
    *,
    role: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AdminUserOut], int]:
    """Sysadmin directory of users with aggregate stats (PRD §41)."""
    conditions = []
    if role:
        conditions.append(User.roles.contains([role]))
    if q:
        pattern = f"%{q}%"
        conditions.append(User.display_name.ilike(pattern) | User.email.ilike(pattern))

    total = await db.scalar(select(func.count()).select_from(User).where(*conditions)) or 0

    row_expr = (
        select(
            User,
            func.coalesce(func.sum(Submission.earned_points), 0),
            func.count().filter(Submission.is_correct),
            func.count(),
        )
        .outerjoin(Submission, Submission.user_id == User.id)
        .where(*conditions)
        .group_by(User.id)
        .order_by(User.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(row_expr)).all()
    return [
        AdminUserOut(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            roles=list(user.roles or []),
            is_active=user.is_active,
            points=int(points),
            solved_count=int(solved),
            attempts=int(attempts),
            created_at=user.created_at,
        )
        for user, points, solved, attempts in rows
    ], int(total)


async def update_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    is_active: bool | None = None,
    roles: list[str] | None = None,
    request: Request | None = None,
) -> AdminUserOut | None:
    """Sysadmin update of a user account (suspend/activate, role adjustment)."""
    user = await db.get(User, user_id)
    if user is None:
        return None

    details: dict[str, Any] = {}
    if is_active is not None and user.is_active != is_active:
        user.is_active = is_active
        details["is_active"] = is_active
    if roles is not None and user.roles != roles:
        user.roles = sorted(set(roles))
        details["roles"] = user.roles
    if details:
        await db.commit()
        await db.refresh(user)

    if "is_active" in details:
        await record_audit(
            db,
            event="user.suspend" if not details["is_active"] else "user.activate",
            user_id=user.id,
            target_id=str(user.id),
            request=request,
        )
    if "roles" in details:
        await record_audit(
            db,
            event="user.roles",
            user_id=user.id,
            target_id=str(user.id),
            details={"roles": user.roles},
            request=request,
        )

    row = (
        await db.execute(
            select(
                User,
                func.coalesce(func.sum(Submission.earned_points), 0),
                func.count().filter(Submission.is_correct),
                func.count(),
            )
            .outerjoin(Submission, Submission.user_id == User.id)
            .where(User.id == user_id)
            .group_by(User.id)
        )
    ).one()
    u, points, solved, attempts = row
    return AdminUserOut(
        id=u.id,
        email=u.email,
        display_name=u.display_name,
        roles=list(u.roles or []),
        is_active=u.is_active,
        points=int(points),
        solved_count=int(solved),
        attempts=int(attempts),
        created_at=u.created_at,
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
