"""Tests for adaptive difficulty and recommendations."""

import uuid

import pytest

from app.core.flags import hash_flag
from app.models import Challenge, User
from app.models.skill_profiles import UserSkillProfile
from app.models.skills import ChallengeSkill, Skill
from app.models.submissions import Submission
from app.services.recommendations import get_recommendations, refresh_difficulty_score

CORRECT = "IIC{test}"


@pytest.mark.asyncio
async def test_difficulty_score_recomputes_after_ten_attempts(test_db):
    async with test_db() as db:
        c = Challenge(
            slug=f"ds_{uuid.uuid4().hex[:6]}",
            title="DS Test",
            description="DS Test",
            category="Linux",
            difficulty="beginner",
            points=10,
            difficulty_score=0.2, # Original seeded
            difficulty_scored_at_count=0,
            flag_hash=hash_flag(CORRECT),
            status="published"
        )
        db.add(c)
        u = User(id=uuid.uuid4(), keycloak_sub="u_ds", email="ds@test.com", display_name="DS")
        db.add(u)
        await db.flush()

        for _ in range(7):
            u_fail = User(id=uuid.uuid4(), keycloak_sub=f"f_{uuid.uuid4().hex[:6]}", display_name="F")
            db.add(u_fail)
            await db.flush()
            db.add(Submission(challenge_id=c.id, user_id=u_fail.id, is_correct=False, earned_points=0))

        for _ in range(3):
            u_pass = User(id=uuid.uuid4(), keycloak_sub=f"p_{uuid.uuid4().hex[:6]}", display_name="P")
            db.add(u_pass)
            await db.flush()
            db.add(Submission(challenge_id=c.id, user_id=u_pass.id, is_correct=True, earned_points=10))

        await db.commit()

        await refresh_difficulty_score(db, c)
        await db.commit()

        # Failures / Total -> 7 / 10 -> 0.70
        assert c.difficulty_score == 0.7
        assert c.difficulty_scored_at_count == 10

@pytest.mark.asyncio
async def test_difficulty_waits_for_ten(test_db):
    async with test_db() as db:
        c = Challenge(
            slug=f"ds_wait_{uuid.uuid4().hex[:6]}",
            title="DS Wait",
            description="Wait",
            category="Linux",
            difficulty="advanced",
            points=100,
            difficulty_score=0.8,
            difficulty_scored_at_count=0,
            status="published"
        )
        db.add(c)
        await db.flush()

        # Add 9 attempts
        for _ in range(9):
            u = User(id=uuid.uuid4(), keycloak_sub=f"u_{uuid.uuid4().hex[:6]}", email="ds@test.com", display_name="DS")
            db.add(u)
            await db.flush()
            db.add(Submission(challenge_id=c.id, user_id=u.id, is_correct=False, earned_points=0))
        await db.commit()

        await refresh_difficulty_score(db, c)
        assert c.difficulty_score == 0.8
        assert c.difficulty_scored_at_count == 0

@pytest.mark.asyncio
async def test_recommendation_ranking(test_db):
    async with test_db() as db:
        user_id = uuid.uuid4()
        u = User(id=user_id, keycloak_sub="u_rec", email="rec@test.com", display_name="REC")

        skill_fav = Skill(slug="fav", name="Fav", is_active=True)
        skill_other = Skill(slug="oth", name="Oth", is_active=True)

        c_fav = Challenge(slug="c_fav", title="FavC", description="Fav", category="X", difficulty="adv", points=50, difficulty_score=0.6, status="published")
        c_oth = Challenge(slug="c_oth", title="OthC", description="Oth", category="X", difficulty="adv", points=50, difficulty_score=0.6, status="published")
        c_solved = Challenge(slug="c_solv", title="SolvC", description="Solv", category="X", difficulty="adv", points=50, difficulty_score=0.6, status="published")

        db.add_all([u, skill_fav, skill_other, c_fav, c_oth, c_solved])
        await db.flush()

        db.add_all([
            ChallengeSkill(challenge_id=c_fav.id, skill_id=skill_fav.id),
            ChallengeSkill(challenge_id=c_oth.id, skill_id=skill_other.id),
            UserSkillProfile(user_id=user_id, skill_id=skill_fav.id, competency_level=80.0),
            UserSkillProfile(user_id=user_id, skill_id=skill_other.id, competency_level=10.0),
            Submission(user_id=user_id, challenge_id=c_solved.id, is_correct=True, earned_points=50)
        ])
        await db.commit()

        recs = await get_recommendations(db, user_id=user_id, limit=5)

        assert len(recs) == 2
        assert recs[0].challenge_id == c_fav.id
        assert recs[1].challenge_id == c_oth.id
