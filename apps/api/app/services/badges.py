"""Evidence-based badge evaluators and grants (Phase 4, PRD §34).

Criteria are stored as JSON on the badge row, e.g. ``{"code": "solver_n",
"value": 15}``. Evaluators run at meaningful events (correct solve, competition
finish) and every grant stores the evidence that satisfied the criteria.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.badges import Badge, UserBadge
from app.models.challenges import Challenge
from app.models.competitions import Competition, CompetitionParticipant, TeamMember
from app.models.labs import LabInstance
from app.models.skills import Skill
from app.models.submissions import Submission
from app.schemas.badge import BadgeCreate, BadgeEarned, BadgeGrantResult, BadgeOut, BadgeUpdate
from app.services.users import record_audit


def _to_out(badge: Badge, skill_name: str | None = None) -> BadgeOut:
    return BadgeOut(
        id=badge.id,
        code=badge.code,
        name=badge.name,
        description=badge.description,
        criteria=badge.criteria,
        icon=badge.icon,
        skill_id=badge.skill_id,
        skill_name=skill_name,
        is_active=badge.is_active,
    )


async def list_badges(
    db: AsyncSession, *, include_inactive: bool = False
) -> list[BadgeOut]:
    conditions = [] if include_inactive else [Badge.is_active.is_(True)]
    badges = (
        await db.scalars(
            select(Badge).where(*conditions).order_by(Badge.created_at.asc())
        )
    ).all()
    skill_ids = {b.skill_id for b in badges if b.skill_id}
    skill_names: dict[uuid.UUID, str] = {}
    if skill_ids:
        rows = (
            await db.execute(
                select(Skill.id, Skill.name).where(Skill.id.in_(skill_ids))
            )
        ).all()
        skill_names = {skill_id: name for skill_id, name in rows}
    return [_to_out(badge, skill_names.get(badge.skill_id)) for badge in badges]


async def get_badge(db: AsyncSession, badge_id: uuid.UUID) -> BadgeOut:
    badge = await db.get(Badge, badge_id)
    if badge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Badge not found")
    return _to_out(badge)


async def create_badge(
    db: AsyncSession, data: BadgeCreate, user_id: uuid.UUID, request: Any = None
) -> BadgeOut:
    existing = await db.scalar(select(Badge).where(Badge.code == data.code))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A badge with this code exists"
        )
    badge = Badge(
        code=data.code,
        name=data.name.strip(),
        description=data.description,
        criteria=data.criteria,
        icon=data.icon,
        skill_id=data.skill_id,
        is_active=data.is_active,
    )
    db.add(badge)
    await db.commit()
    await db.refresh(badge)
    await record_audit(
        db, event="badge.create", user_id=user_id, target_id=badge.code, request=request
    )
    return _to_out(badge)


async def update_badge(
    db: AsyncSession,
    badge: Badge,
    data: BadgeUpdate,
    user_id: uuid.UUID,
    request: Any = None,
) -> BadgeOut:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(badge, field, value)
    await db.commit()
    await db.refresh(badge)
    await record_audit(
        db, event="badge.update", user_id=user_id, target_id=badge.code, request=request
    )
    return _to_out(badge)


async def delete_badge(
    db: AsyncSession, badge: Badge, user_id: uuid.UUID, request: Any = None
) -> None:
    code = badge.code
    await db.delete(badge)
    await db.commit()
    await record_audit(
        db, event="badge.delete", user_id=user_id, target_id=code, request=request
    )


# --- Evaluators -------------------------------------------------------------


async def _context(db: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    """Cheap user summary shared by all evaluators."""
    solved_count = int(
        await db.scalar(
            select(func.count(func.distinct(Submission.challenge_id))).where(
                Submission.user_id == user_id, Submission.is_correct.is_(True)
            )
        )
        or 0
    )
    category_rows = (
        await db.execute(
            select(Challenge.category, func.count(func.distinct(Challenge.id)))
            .join(Submission, Submission.challenge_id == Challenge.id)
            .where(
                Submission.user_id == user_id,
                Submission.is_correct.is_(True),
            )
            .group_by(Challenge.category)
        )
    ).all()
    categories = {category: int(n) for category, n in category_rows}

    lab_sessions = int(
        await db.scalar(
            select(func.count()).select_from(LabInstance).where(LabInstance.user_id == user_id)
        )
        or 0
    )

    from app.services.skills import compute_user_scores

    skill_scores = await compute_user_scores(db, user_id)

    return {
        "solved_count": solved_count,
        "categories": categories,
        "lab_sessions": lab_sessions,
        "skill_scores": {str(skill_id): data["score"] for skill_id, data in skill_scores.items()},
    }


async def _evaluate(
    db: AsyncSession,
    badge: Badge,
    user_id: uuid.UUID,
    ctx: dict[str, Any],
) -> list[str] | None:
    """Return evidence references if the user satisfies the badge, else None."""
    code = (badge.criteria or {}).get("code", badge.code)
    value = int((badge.criteria or {}).get("value") or 0)

    if code == "first_solve":
        return ["first solve"] if ctx["solved_count"] >= 1 else None

    if code == "solver_n":
        return (
            [f"{ctx['solved_count']} challenges solved"]
            if ctx["solved_count"] >= max(value, 1)
            else None
        )

    if code == "category_champion":
        category = (badge.criteria or {}).get("category")
        count = ctx["categories"].get(category, 0)
        if category and count >= max(value, 1):
            return [f"{count} {category} challenges solved"]
        return None

    if code == "skill_score":
        threshold = max(value, 1)
        high = sorted(
            (sid for sid, score in ctx["skill_scores"].items() if score >= threshold),
            key=lambda sid: -ctx["skill_scores"][sid],
        )
        return [f"skill score {ctx['skill_scores'][sid]}" for sid in high[:2]] or None

    if code == "lab_session":
        return ["docker lab launched"] if ctx["lab_sessions"] >= 1 else None

    if code == "ctf_participant":
        return await _competition_participant_proof(db, user_id)

    if code == "ctf_winner":
        return await _competition_winner_proof(db, user_id, top_n=max(value, 1))

    return None


async def _competition_participant_proof(
    db: AsyncSession, user_id: uuid.UUID
) -> list[str] | None:
    slugs = list(
        (
            await db.execute(
                select(Competition.slug)
                .join(
                    CompetitionParticipant,
                    CompetitionParticipant.competition_id == Competition.id,
                )
                .where(
                    CompetitionParticipant.user_id == user_id,
                    Competition.status.in_(("live", "finished", "archived")),
                )
            )
        ).scalars().all()
    )
    return [f"participated in {slug}" for slug in slugs] if slugs else None


async def _competition_winner_proof(
    db: AsyncSession, user_id: uuid.UUID, top_n: int
) -> list[str] | None:
    from app.services import competitions as competition_service

    finished = (await db.scalars(select(Competition).where(Competition.status == "finished"))).all()
    wins: list[str] = []
    for competition in finished:
        entries = await competition_service.leaderboard(db, competition)
        for entry in entries[:top_n]:
            if entry.entity_type == "user" and entry.entity_id == user_id:
                wins.append(competition.slug)
                break
            if entry.entity_type == "team":
                member = await db.scalar(
                    select(TeamMember.user_id).where(
                        TeamMember.team_id == entry.entity_id,
                        TeamMember.user_id == user_id,
                    )
                )
                if member:
                    wins.append(competition.slug)
                    break
    return [f"top-{top_n} in {slug}" for slug in wins] if wins else None


async def earned_badges(db: AsyncSession, user_id: uuid.UUID) -> list[BadgeEarned]:
    rows = (
        await db.execute(
            select(UserBadge, Badge)
            .join(Badge, Badge.id == UserBadge.badge_id)
            .where(UserBadge.user_id == user_id)
            .order_by(UserBadge.earned_at.asc())
        )
    ).all()
    skill_ids = {badge.skill_id for _, badge in rows if badge.skill_id}
    skills: dict[uuid.UUID, str] = {}
    if skill_ids:
        skills = dict(
            (await db.execute(select(Skill.id, Skill.name).where(Skill.id.in_(skill_ids)))).all()
        )
    return [
        BadgeEarned(
            id=ub.id,
            code=badge.code,
            name=badge.name,
            description=badge.description,
            icon=badge.icon,
            skill_name=skills.get(badge.skill_id),
            earned_at=ub.earned_at,
            evidence=ub.evidence,
        )
        for ub, badge in rows
    ]


async def grant_eligible_badges(
    db: AsyncSession, user_id: uuid.UUID, request: Any = None
) -> BadgeGrantResult:
    """Grant every active badge the user is newly eligible for.

    Called after meaningful events (correct solve, competition finish). New
    grants are audited with the same request that triggered the event.
    """
    badges = (await db.scalars(select(Badge).where(Badge.is_active.is_(True)))).all()
    if not badges:
        return BadgeGrantResult()
    ctx = await _context(db, user_id)
    owned = set(
        (await db.execute(select(UserBadge.badge_id).where(UserBadge.user_id == user_id)))
        .scalars()
        .all()
    )
    result = BadgeGrantResult()
    new_grants: list[Badge] = []
    for badge in badges:
        if badge.id in owned:
            result.already_earned.append(badge.code)
            continue
        evidence = await _evaluate(db, badge, user_id, ctx)
        if evidence is None:
            continue
        db.add(
            UserBadge(
                user_id=user_id,
                badge_id=badge.id,
                evidence={"refs": evidence, "badge": badge.code},
            )
        )
        result.granted.append(badge.code)
        new_grants.append(badge)
    await db.commit()
    for badge in new_grants:
        await record_audit(
            db,
            event="badge.grant",
            user_id=user_id,
            target_id=badge.code,
            details={"granted": True},
            request=request,
        )
    return result