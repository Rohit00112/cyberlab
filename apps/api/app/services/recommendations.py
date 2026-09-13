"""Difficulty scoring and recommendations logic (Phase 5, §28)."""
from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.challenges import Challenge
from app.models.skill_profiles import UserSkillProfile
from app.models.skills import ChallengeSkill, Skill
from app.models.submissions import Submission
from app.schemas.recommendation import ChallengeRecommendationOut
from app.schemas.skill import SkillBrief


async def refresh_difficulty_score(db: AsyncSession, challenge: Challenge) -> None:
    """Recomputes standard ELO-adjacent difficulty score after every 10 fresh attempts."""
    total_unfiltered = await db.scalar(
        select(func.count(Submission.id)).where(Submission.challenge_id == challenge.id)
    )
    total = int(total_unfiltered or 0)

    if total - challenge.difficulty_scored_at_count < 10:
        return

    solves_unfiltered = await db.scalar(
        select(func.count(Submission.id)).where(
            Submission.challenge_id == challenge.id,
            Submission.is_correct.is_(True),
        )
    )
    solves = int(solves_unfiltered or 0)

    # score = failures / total
    score = (total - solves) / total if total > 0 else 0.2

    challenge.difficulty_score = max(0.0, min(1.0, score))
    challenge.difficulty_scored_at_count = total
    # Caller owns commit.
    db.add(challenge)
    await db.flush()


async def refresh_challenge_difficulty_after_submission(db: AsyncSession, challenge_id: uuid.UUID) -> None:
    """Helper invoked downstream from flag submission."""
    challenge = await db.get(Challenge, challenge_id)
    if challenge:
        await refresh_difficulty_score(db, challenge)


async def get_recommendations(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 10
) -> list[ChallengeRecommendationOut]:
    """Dynamically recommend next best challenges using explicit competency."""
    limit = min(max(limit, 1), 50)

    # 1. Fetch solved challenges for exclusion
    solved_challenge_ids = set((
        await db.scalars(
            select(Submission.challenge_id)
            .where(Submission.user_id == user_id, Submission.is_correct.is_(True))
        )
    ).all())

    # 2. Fetch UserSkillProfile map
    profiles = (
        await db.scalars(
            select(UserSkillProfile).where(UserSkillProfile.user_id == user_id)
        )
    ).all()
    user_competency = {p.skill_id: p.competency_level for p in profiles}

    # 3. Query unsolved published challenges + skills
    rows = (
        await db.execute(
            select(Challenge, Skill)
            .outerjoin(ChallengeSkill, Challenge.id == ChallengeSkill.challenge_id)
            .outerjoin(Skill, Skill.id == ChallengeSkill.skill_id)
            .where(Challenge.status == "published")
        )
    ).all()

    # Base challenges
    challenge_map: dict[uuid.UUID, dict] = {}
    for challenge, skill in rows:
        if challenge.id in solved_challenge_ids:
            continue

        if challenge.id not in challenge_map:
            challenge_map[challenge.id] = {"challenge": challenge, "skills": []}

        if skill is not None:
            challenge_map[challenge.id]["skills"].append(skill)

    # Calculate scores
    scored_challenges = []

    if not user_competency:
        # Fallback for brand new users - order by points ascending (beginner first)
        challenge_list = list(challenge_map.values())
        challenge_list.sort(key=lambda x: x["challenge"].points)
        scored_challenges = [{"c": x, "score": 0.0} for x in challenge_list[:limit]]
    else:
        user_avg = sum(user_competency.values()) / len(user_competency)

        for ch_data in challenge_map.values():
            c = cast(Challenge, ch_data["challenge"])
            skills = cast(list[Skill], ch_data["skills"])

            # Skill match
            if skills:
                skill_match = sum(user_competency.get(s.id, 0.0) for s in skills) / len(skills)
            else:
                skill_match = 0.0

            # Difficulty gap mapping [0-1] to [0-100] scale
            difficulty_gap = abs(user_avg - (c.difficulty_score * 100))
            score = skill_match - (difficulty_gap * 0.3)

            scored_challenges.append({"c": ch_data, "score": score})

        scored_challenges.sort(key=lambda x: x["score"], reverse=True)
        scored_challenges = scored_challenges[:limit]

    return [
        ChallengeRecommendationOut(
            challenge_id=item["c"]["challenge"].id,
            slug=item["c"]["challenge"].slug,
            title=item["c"]["challenge"].title,
            category=item["c"]["challenge"].category,
            difficulty=item["c"]["challenge"].difficulty,
            points=item["c"]["challenge"].points,
            difficulty_score=item["c"]["challenge"].difficulty_score,
            recommendation_score=item["score"],
            skills=[SkillBrief(id=s.id, slug=s.slug, name=s.name, icon=s.icon) for s in item["c"]["skills"]],
        )
        for item in scored_challenges
    ]
