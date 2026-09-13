"""Skill taxonomy, competency scoring and analytics (Phase 4, PRD §25-28).

Competency model (PRD §25 — not a simple average):

    weight(c)  = earned_points(c) * difficulty_weight(difficulty)
    score      = min(100, round(100 * (1 - 0.5 ** (sum(weight) / 500))))

``earned_points`` already reflects hint penalties, and the asymptotic curve
rewards breadth without letting any single challenge max out a skill.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from statistics import median
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.badges import Badge, UserBadge
from app.models.challenges import Challenge
from app.models.hint_reveals import HintReveal
from app.models.skills import ChallengeSkill, Skill
from app.models.submissions import Submission
from app.models.users import User
from app.schemas.skill import (
    ChallengeAttemptOut,
    ChallengeDifficultyOut,
    SkillAggregate,
    SkillBrief,
    SkillCreate,
    SkillEvidence,
    SkillOut,
    SkillProfileOut,
    SkillScore,
    SkillUpdate,
    StudentAnalyticsOut,
)
from app.services.users import record_audit

DIFFICULTY_WEIGHT: dict[str, float] = {
    "beginner": 1.0,
    "intermediate": 1.5,
    "advanced": 2.25,
}
SCORE_HALF_LEVEL = 500.0


def _difficulty_weight(difficulty: str | None) -> float:
    return DIFFICULTY_WEIGHT.get(difficulty or "", 1.0)


def _skill_score(sum_units: float) -> int:
    return min(100, round(100 * (1 - 0.5 ** (sum_units / SCORE_HALF_LEVEL))))


# Free-form skill strings on challenges reconciled to taxonomy slugs
# (keys are already ``_normalize``d: lowercased, "/" -> " ").
_SKILL_ALIASES: dict[str, str] = {
    "packet basics": "networking",
    "tcp ip": "networking",
    "email headers": "networking",
    "spf dkim awareness": "networking",
    "linux cli": "linux",
    "filesystem": "linux",
    "basic command usage": "linux",
    "bash scripting": "linux",
    "linux permissions": "linux",
    "suid": "linux",
    "enumeration": "linux",
    "web enumeration": "web-security",
    "sql": "web-security",
    "auth bypass": "web-security",
    "xor": "cryptography",
    "pattern recognition": "cryptography",
    "exif": "digital-forensics",
    "metadata analysis": "digital-forensics",
    "forensics tooling": "digital-forensics",
    "phishing analysis": "security-operations",
    "c": "secure-coding",
    "buffer handling": "secure-coding",
    "code review": "secure-coding",
}


def _normalize(name: str) -> str:
    return " ".join(name.strip().lower().replace("/", " ").split())


async def sync_challenge_skills(
    db: AsyncSession, challenge_id: uuid.UUID, skill_names: list[str] | None
) -> None:
    """Reconcile ``challenge_skills`` rows from a challenge's free-form skills.

    Matches both taxonomy slugs/names and the seeded alias map. Idempotent.
    """
    await db.execute(
        ChallengeSkill.__table__.delete().where(ChallengeSkill.challenge_id == challenge_id)
    )
    if not skill_names:
        await db.commit()
        return
    linked: set[uuid.UUID] = set()
    skills = (await db.scalars(select(Skill))).all()
    by_key: dict[str, Skill] = {}
    for skill in skills:
        by_key[skill.slug] = skill
        by_key[_normalize(skill.name)] = skill
    for raw in skill_names:
        key = _normalize(raw)
        skill = by_key.get(key) or by_key.get(_SKILL_ALIASES.get(key, ""))
        if skill is not None:
            linked.add(skill.id)
    for skill_id in linked:
        db.add(ChallengeSkill(challenge_id=challenge_id, skill_id=skill_id))
    await db.commit()


async def list_skills(
    db: AsyncSession,
    *,
    include_inactive: bool = False,
    with_counts: bool = False,
) -> list[SkillOut]:
    conditions = [] if include_inactive else [Skill.is_active.is_(True)]
    skills = (
        await db.scalars(select(Skill).where(*conditions).order_by(Skill.name.asc()))
    ).all()
    by_id = {skill.id: skill for skill in skills}
    counts: dict[uuid.UUID, int] = {}
    if with_counts:
        rows = (
            await db.execute(
                select(ChallengeSkill.skill_id, func.count(ChallengeSkill.challenge_id))
                .group_by(ChallengeSkill.skill_id)
            )
        ).all()
        counts = {skill_id: int(n) for skill_id, n in rows}
    result: list[SkillOut] = []
    for skill in skills:
        parent = by_id.get(skill.parent_id) if skill.parent_id else None
        path = f"{parent.name} / {skill.name}" if parent else skill.name
        result.append(
            SkillOut(
                id=skill.id,
                slug=skill.slug,
                name=skill.name,
                description=skill.description,
                path=path,
                icon=skill.icon,
                is_active=skill.is_active,
                challenge_count=counts.get(skill.id, 0),
            )
        )
    return result


async def create_skill(
    db: AsyncSession, data: SkillCreate, user_id: uuid.UUID, request: Any = None
) -> SkillOut:
    slug = data.slug.strip().lower().replace(" ", "-")
    existing = await db.scalar(select(Skill).where(Skill.slug == slug))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A skill with this slug exists"
        )
    skill = Skill(
        slug=slug,
        name=data.name.strip(),
        description=data.description,
        parent_id=data.parent_id,
        icon=data.icon,
        is_active=data.is_active,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    await record_audit(
        db, event="skill.create", user_id=user_id, target_id=slug, request=request
    )
    return _to_out_skill(skill)


async def update_skill(
    db: AsyncSession,
    skill: Skill,
    data: SkillUpdate,
    user_id: uuid.UUID,
    request: Any = None,
) -> SkillOut:
    updates = data.model_dump(exclude_unset=True)
    if "slug" in updates and updates["slug"]:
        slug = updates["slug"].strip().lower().replace(" ", "-")
        if slug != skill.slug and await db.scalar(select(Skill).where(Skill.slug == slug)):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="A skill with this slug exists"
            )
        updates["slug"] = slug
    for field, value in updates.items():
        setattr(skill, field, value)
    await db.commit()
    await db.refresh(skill)
    await record_audit(
        db, event="skill.update", user_id=user_id, target_id=skill.slug, request=request
    )
    return _to_out_skill(skill)


def _to_out_skill(skill: Skill) -> SkillOut:
    return SkillOut(
        id=skill.id,
        slug=skill.slug,
        name=skill.name,
        description=skill.description,
        path=skill.name,
        icon=skill.icon,
        is_active=skill.is_active,
        challenge_count=0,
    )


async def get_skill(db: AsyncSession, skill_id: uuid.UUID) -> Skill:
    skill = await db.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    return skill


async def _briefs(db: AsyncSession) -> dict[uuid.UUID, SkillBrief]:
    rows = (await db.execute(select(Skill.id, Skill.slug, Skill.name, Skill.icon))).all()
    return {
        skill_id: SkillBrief(id=skill_id, slug=slug, name=name, icon=icon)
        for skill_id, slug, name, icon in rows
    }


async def compute_user_scores(
    db: AsyncSession, user_id: uuid.UUID
) -> dict[uuid.UUID, dict[str, Any]]:
    """Per-skill competency for one user (score + evidence)."""
    rows = (
        await db.execute(
            select(
                ChallengeSkill.skill_id,
                Challenge.id,
                Challenge.title,
                Challenge.difficulty,
                Submission.earned_points,
                Submission.created_at,
            )
            .join(Challenge, Challenge.id == ChallengeSkill.challenge_id)
            .join(Submission, Submission.challenge_id == Challenge.id)
            .where(Submission.user_id == user_id, Submission.is_correct.is_(True))
            .order_by(Submission.created_at.asc())
        )
    ).all()

    buckets: dict[uuid.UUID, dict[str, Any]] = {}
    for skill_id, challenge_id, title, difficulty, earned, solved_at in rows:
        bucket = buckets.setdefault(
            skill_id,
            {"sum_units": 0.0, "solved": 0, "points": 0, "evidence": []},
        )
        bucket["sum_units"] += float(earned or 0) * _difficulty_weight(difficulty)
        bucket["solved"] += 1
        bucket["points"] += int(earned or 0)
        bucket["evidence"].append(
            SkillEvidence(
                challenge_id=challenge_id,
                challenge_title=title,
                difficulty=difficulty,
                earned_points=int(earned or 0),
                solved_at=solved_at,
            )
        )
    for bucket in buckets.values():
        bucket["score"] = _skill_score(bucket["sum_units"])
    return buckets


async def get_skill_profile(
    db: AsyncSession, user_id: uuid.UUID, *, include_zero: bool = True
) -> SkillProfileOut:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    buckets = await compute_user_scores(db, user_id)
    briefs = await _briefs(db)

    skills: list[SkillScore] = []
    active = (
        await db.scalars(select(Skill).where(Skill.is_active.is_(True)).order_by(Skill.name))
    ).all()
    for skill in active:
        bucket = buckets.get(skill.id)
        if bucket is not None or include_zero:
            skills.append(
                SkillScore(
                    skill=briefs[skill.id],
                    score=bucket["score"] if bucket else 0,
                    solved_count=bucket["solved"] if bucket else 0,
                    total_points=bucket["points"] if bucket else 0,
                    evidence=bucket["evidence"] if bucket else [],
                )
            )
    skills.sort(key=lambda s: (-s.score, s.skill.name))

    totals = (
        await db.execute(
            select(
                func.coalesce(func.sum(Submission.earned_points), 0),
                func.count().filter(Submission.is_correct),
            ).where(Submission.user_id == user_id)
        )
    ).one()
    total_points, solved_count = totals
    return SkillProfileOut(
        user_id=user.id,
        display_name=user.display_name,
        total_points=int(total_points),
        solved_count=int(solved_count),
        skills=skills,
    )


async def skill_analytics(db: AsyncSession) -> list[SkillAggregate]:
    """Per-skill aggregate across all students (PRD §27 skill analytics)."""
    rows = (
        await db.execute(
            select(
                ChallengeSkill.skill_id,
                Submission.user_id,
                Submission.earned_points,
                Challenge.difficulty,
            )
            .join(Challenge, Challenge.id == ChallengeSkill.challenge_id)
            .join(Submission, Submission.challenge_id == Challenge.id)
            .where(Submission.is_correct.is_(True))
        )
    ).all()

    per_skill: dict[uuid.UUID, dict[str, Any]] = {}
    for skill_id, user_id, earned, difficulty in rows:
        skill = per_skill.setdefault(
            skill_id, {"users": {}, "solves": 0, "points": 0}
        )
        user_units = skill["users"].setdefault(user_id, 0.0)
        skill["users"][user_id] = user_units + float(earned or 0) * _difficulty_weight(
            difficulty
        )
        skill["solves"] += 1
        skill["points"] += int(earned or 0)

    briefs = await _briefs(db)
    aggregates: list[SkillAggregate] = []
    for skill_id, stat in per_skill.items():
        scores = [_skill_score(u) for u in stat["users"].values()]
        aggregates.append(
            SkillAggregate(
                skill=briefs[skill_id],
                students_with_evidence=len(stat["users"]),
                total_solves=stat["solves"],
                total_points=stat["points"],
                avg_score=round(sum(scores) / len(scores), 1) if scores else 0.0,
            )
        )
    aggregates.sort(key=lambda a: (-a.students_with_evidence, a.skill.name))
    return aggregates


async def challenge_difficulty_stats(
    db: AsyncSession, challenge_id: uuid.UUID
) -> ChallengeDifficultyOut:
    challenge = await db.get(Challenge, challenge_id)
    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found"
        )

    attempts = int(
        await db.scalar(
            select(func.count()).select_from(Submission).where(
                Submission.challenge_id == challenge_id
            )
        )
        or 0
    )
    distinct_students = int(
        await db.scalar(
            select(func.count(func.distinct(Submission.user_id))).where(
                Submission.challenge_id == challenge_id
            )
        )
        or 0
    )

    solvers = int(
        await db.scalar(
            select(func.count(func.distinct(Submission.user_id))).where(
                Submission.challenge_id == challenge_id,
                Submission.is_correct.is_(True),
            )
        )
        or 0
    )
    hint_users = int(
        await db.scalar(
            select(func.count(func.distinct(HintReveal.user_id))).where(
                HintReveal.challenge_id == challenge_id
            )
        )
        or 0
    )

    median_seconds: float | None = None
    if solvers:
        rows = (
            await db.execute(
                select(Submission.user_id, Submission.created_at, Submission.is_correct)
                .where(Submission.challenge_id == challenge_id)
                .order_by(Submission.created_at.asc())
            )
        ).all()
        by_user: dict[uuid.UUID, dict[str, Any]] = {}
        for user_id, created_at, is_correct in rows:
            entry = by_user.setdefault(user_id, {"first": created_at, "solved": None})
            if is_correct and entry["solved"] is None:
                entry["solved"] = created_at
        deltas = []
        for entry in by_user.values():
            if entry["solved"] is not None and entry["first"] is not None:
                deltas.append((entry["solved"] - entry["first"]).total_seconds())
        if deltas:
            median_seconds = round(median(deltas), 1)

    success_rate = (
        round(solvers / distinct_students, 4) if distinct_students else 0.0
    )
    avg_attempts = (
        round(attempts / distinct_students, 2) if distinct_students else 0.0
    )
    hint_usage = round(hint_users / distinct_students, 4) if distinct_students else 0.0

    if distinct_students == 0:
        verdict = "insufficient_data"
    elif success_rate > 0.8:
        verdict = "too_easy"
    elif success_rate < 0.3:
        verdict = "too_difficult"
    elif hint_usage > 0.6 and success_rate < 0.5:
        verdict = "challenging"
    else:
        verdict = "appropriate"

    return ChallengeDifficultyOut(
        challenge_id=challenge.id,
        slug=challenge.slug,
        title=challenge.title,
        estimated_minutes=challenge.estimated_minutes,
        attempts=attempts,
        distinct_students=distinct_students,
        solvers=solvers,
        success_rate=success_rate,
        median_seconds=median_seconds,
        avg_attempts_per_student=avg_attempts,
        hint_users=hint_users,
        hint_usage=hint_usage,
        verdict=verdict,
    )


async def student_analytics(db: AsyncSession, user_id: uuid.UUID) -> StudentAnalyticsOut:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    totals = (
        await db.execute(
            select(
                func.coalesce(func.sum(Submission.earned_points), 0),
                func.count().filter(Submission.is_correct),
                func.count(),
            ).where(Submission.user_id == user_id)
        )
    ).one()
    total_points, solved_count, attempts = totals

    hint_reveals = int(
        await db.scalar(
            select(func.count()).select_from(HintReveal).where(HintReveal.user_id == user_id)
        )
        or 0
    )

    rows = (
        await db.execute(
            select(
                Challenge.id,
                Challenge.slug,
                Challenge.title,
                Challenge.category,
                Challenge.points,
                Submission.is_correct,
                Submission.earned_points,
                Submission.created_at,
            )
            .join(Submission, Submission.challenge_id == Challenge.id)
            .where(Submission.user_id == user_id)
            .order_by(Submission.created_at.asc())
        )
    ).all()
    per_challenge: dict[uuid.UUID, dict[str, Any]] = {}
    for challenge_id, slug, title, category, points, is_correct, earned, created_at in rows:
        entry = per_challenge.setdefault(
            challenge_id,
            {
                "challenge_id": challenge_id,
                "slug": slug,
                "title": title,
                "category": category,
                "points": points,
                "attempts": 0,
                "solved": False,
                "earned_points": 0,
                "first_attempt_at": created_at,
                "solved_at": None,
            },
        )
        entry["attempts"] += 1
        if entry["first_attempt_at"] is None:
            entry["first_attempt_at"] = created_at
        if is_correct and not entry["solved"]:
            entry["solved"] = True
            entry["earned_points"] = int(earned or 0)
            entry["solved_at"] = created_at

    hint_rows = (
        await db.execute(
            select(HintReveal.challenge_id, func.count(HintReveal.id))
            .where(HintReveal.user_id == user_id)
            .group_by(HintReveal.challenge_id)
        )
    ).all()
    hints_map = {str(cid): int(n) for cid, n in hint_rows}

    challenges: list[ChallengeAttemptOut] = []
    for entry in per_challenge.values():
        challenges.append(
            ChallengeAttemptOut(
                **{
                    k: v
                    for k, v in entry.items()
                    if k in ChallengeAttemptOut.model_fields
                },
                hints_revealed=hints_map.get(str(entry["challenge_id"]), 0),
            )
        )
    challenges.sort(key=lambda c: c.solved_at or datetime.max.replace(tzinfo=UTC))

    earned_badges = (
        await db.execute(
            select(Badge.code, Badge.name, Badge.icon, UserBadge.earned_at, UserBadge.evidence)
            .join(UserBadge, UserBadge.badge_id == Badge.id)
            .where(UserBadge.user_id == user_id)
            .order_by(UserBadge.earned_at.asc())
        )
    ).all()
    badges = [
        {
            "code": code,
            "name": name,
            "icon": icon,
            "earned_at": earned_at.isoformat() if earned_at else None,
            "evidence": evidence,
        }
        for code, name, icon, earned_at, evidence in earned_badges
    ]

    profile = await get_skill_profile(db, user_id, include_zero=False)
    return StudentAnalyticsOut(
        user_id=user.id,
        display_name=user.display_name,
        email=user.email,
        total_points=int(total_points),
        solved_count=int(solved_count),
        attempts=int(attempts),
        hint_reveals=hint_reveals,
        badges=badges,
        challenges=challenges,
        skills=profile.skills,
    )