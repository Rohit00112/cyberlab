"""Shared plumbing for the live recommendation backends (Phase 7, PRD §72).

The entry point is `recommendations.get_recommendations`, which:
  1. builds a candidate pool once (unsolved published challenges + competency),
  2. dispatches to the configured backend (rule | graph | gnn),
  3. falls back to the `rule` backend on any backend failure so recommendations
     are never empty, and
  4. logs a RecommendationLog row tagged with the backend `source`.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.challenges import Challenge
from app.models.skill_profiles import UserSkillProfile
from app.models.skills import ChallengeSkill, Skill
from app.models.submissions import Submission


class RecommenderError(RuntimeError):
    """Raised when a configured backend cannot produce recommendations."""


def skill_match(
    challenge: Challenge, skills: list[Skill], user_competency: dict[uuid.UUID, float]
) -> float:
    """Mean competency across the challenge's skills (0 when untagged)."""
    if not skills:
        return 0.0
    return sum(user_competency.get(s.id, 0.0) for s in skills) / len(skills)


def difficulty_gap(challenge: Challenge, user_avg: float) -> float:
    return abs(user_avg - (challenge.difficulty_score * 100))


async def candidate_pool(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[set[uuid.UUID], list[dict], dict[uuid.UUID, float]]:
    """Fetch solved ids, unsolved published challenges with skills, and competency."""
    solved_challenge_ids = set((
        await db.scalars(
            select(Submission.challenge_id)
            .where(Submission.user_id == user_id, Submission.is_correct.is_(True))
        )
    ).all())

    profiles = (
        await db.scalars(select(UserSkillProfile).where(UserSkillProfile.user_id == user_id))
    ).all()
    user_competency = {p.skill_id: p.competency_level for p in profiles}

    rows = (
        await db.execute(
            select(Challenge, Skill)
            .outerjoin(ChallengeSkill, Challenge.id == ChallengeSkill.challenge_id)
            .outerjoin(Skill, Skill.id == ChallengeSkill.skill_id)
            .where(Challenge.status == "published")
        )
    ).all()

    challenge_map: dict[uuid.UUID, dict] = {}
    for challenge, skill in rows:
        if challenge.id in solved_challenge_ids:
            continue
        if challenge.id not in challenge_map:
            challenge_map[challenge.id] = {"challenge": challenge, "skills": []}
        if skill is not None:
            challenge_map[challenge.id]["skills"].append(skill)

    candidates = list(challenge_map.values())
    return solved_challenge_ids, candidates, user_competency


async def recommend_rule(
    candidates: list[dict], user_competency: dict[uuid.UUID, float], limit: int
) -> list[dict]:
    """Baseline recommender (Phase 5 §28): skill-match minus difficulty gap."""
    if not user_competency:
        ordered = sorted(candidates, key=lambda x: x["challenge"].points)
        for item in ordered[:limit]:
            item["score"] = 0.0
        return ordered[:limit]

    user_avg = sum(user_competency.values()) / len(user_competency)
    scored = []
    for item in candidates:
        challenge = item["challenge"]
        score = skill_match(challenge, item["skills"], user_competency) - (
            difficulty_gap(challenge, user_avg) * 0.3
        )
        item["score"] = score
        scored.append((item, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [item for item, _ in scored[:limit]]