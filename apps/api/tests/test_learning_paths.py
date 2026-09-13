"""Tests for learning path progress."""

import uuid

import pytest

from app.models import Challenge, User
from app.models.learning_paths import LearningPath, LearningPathStep
from app.models.submissions import Submission
from app.services.learning_paths import get_path_with_progress


@pytest.mark.asyncio
async def test_path_progress_marks_completed_unlocked_locked(test_db):
    async with test_db() as db:
        user_id = uuid.uuid4()
        u = User(id=user_id, keycloak_sub="u_path", email="path@test.com", display_name="Path")
        db.add(u)

        p = LearningPath(slug="test-path", title="Test Path", is_published=True)
        db.add(p)
        await db.flush()

        challenges = []
        for i in range(3):
            c = Challenge(
                slug=f"c_path_{i}",
                title=f"Path {i}",
                description="desc",
                category="Linux",
                difficulty="beginner",
                points=10,
                status="published"
            )
            db.add(c)
            challenges.append(c)

        await db.flush()

        for i, c in enumerate(challenges):
            db.add(LearningPathStep(learning_path_id=p.id, challenge_id=c.id, step_order=i))

        # Solve only the FIRST challenge (index 0)
        db.add(Submission(user_id=user_id, challenge_id=challenges[0].id, is_correct=True, earned_points=10))
        await db.commit()

        detail = await get_path_with_progress(db, path_id=p.id, user_id=user_id)

        assert len(detail.steps) == 3
        # First is solved => completed
        assert detail.steps[0].status == "completed"
        # Second is first unsolved => unlocked
        assert detail.steps[1].status == "unlocked"
        # Third is subsequent => locked
        assert detail.steps[2].status == "locked"

@pytest.mark.asyncio
async def test_finished_path_has_no_unlocked_step(test_db):
    async with test_db() as db:
        user_id = uuid.uuid4()
        u = User(id=user_id, keycloak_sub="u_path2", email="path2@test.com", display_name="Path")
        p = LearningPath(slug="test-path-2", title="Test Path 2", is_published=True)
        db.add_all([u, p])
        await db.flush()

        c = Challenge(slug="c_solv", title="C", description="desc", category="Linux", difficulty="beginner", points=10, status="published")
        db.add(c)
        await db.flush()

        db.add(LearningPathStep(learning_path_id=p.id, challenge_id=c.id, step_order=0))
        db.add(Submission(user_id=user_id, challenge_id=c.id, is_correct=True, earned_points=10))
        await db.commit()

        detail = await get_path_with_progress(db, path_id=p.id, user_id=user_id)
        assert len(detail.steps) == 1
        assert detail.steps[0].status == "completed"
