"""Explicit user skill competency service."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.challenges import Challenge
from app.models.skill_profiles import UserSkillProfile
from app.models.skills import ChallengeSkill, Skill
from app.schemas.skill_profile import SkillProfileOut


async def update_profiles_for_solve(db: AsyncSession, *, user_id: uuid.UUID, challenge: Challenge) -> None:
    """Increment user competency for all skills linked to this challenge.

    This does NOT commit; caller must commit the transaction.
    Gain is bounded to max 100.
    """
    links = (
        await db.scalars(
            select(ChallengeSkill).where(ChallengeSkill.challenge_id == challenge.id)
        )
    ).all()

    for link in links:
        profile = await db.scalar(
            select(UserSkillProfile).where(
                UserSkillProfile.user_id == user_id,
                UserSkillProfile.skill_id == link.skill_id,
            )
        )
        if profile is None:
            profile = UserSkillProfile(
                user_id=user_id,
                skill_id=link.skill_id,
                competency_level=0.0,
            )
            db.add(profile)
            await db.flush()

        gain = max(0.5, challenge.difficulty_score) * 10
        profile.competency_level = min(100.0, profile.competency_level + gain)
        profile.last_updated = datetime.now(UTC)


async def get_user_skill_profiles(db: AsyncSession, user_id: uuid.UUID) -> list[SkillProfileOut]:
    """Get all explicit competency profiles for user."""
    rows = (
        await db.execute(
            select(UserSkillProfile, Skill)
            .join(Skill, Skill.id == UserSkillProfile.skill_id)
            .where(UserSkillProfile.user_id == user_id)
            .order_by(UserSkillProfile.competency_level.desc(), Skill.name.asc())
        )
    ).all()

    return [
        SkillProfileOut(
            user_id=profile.user_id,
            skill_id=profile.skill_id,
            skill_slug=skill.slug,
            skill_name=skill.name,
            competency_level=profile.competency_level,
            last_updated=profile.last_updated,
        )
        for profile, skill in rows
    ]
