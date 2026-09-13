"""Tests for adaptive learning models."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.models import Challenge, User  # noqa: F401  (registers tables)

# Import the new models to test they exist
from app.models.learning_paths import LearningPath, LearningPathStep  # noqa: F401
from app.models.skill_profiles import UserSkillProfile  # noqa: F401


@pytest.fixture
async def test_db():
    """Create a fresh test database."""
    url = get_settings().database_url
    test_url = f"{url.rsplit('/', 1)[0]}/cyberlab_test"
    engine = create_async_engine(test_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def test_adaptive_tables_exist(test_db):
    """Verify that adaptive learning tables exist in the database."""
    async with test_db() as db:
        # Check LearningPath table exists
        result = await db.execute(select(LearningPath))
        assert result is not None

        # Check LearningPathStep table exists
        result = await db.execute(select(LearningPathStep))
        assert result is not None

        # Check UserSkillProfile table exists
        result = await db.execute(select(UserSkillProfile))
        assert result is not None


async def test_challenge_has_difficulty_score(test_db):
    """Verify that challenges have difficulty_score column."""
    async with test_db() as db:
        # Create a test challenge
        challenge = Challenge(
            slug=f"test-{uuid.uuid4().hex[:6]}",
            title="Test Challenge",
            description="Test description",
            category="test",
            difficulty="beginner",
            points=100,
        )
        db.add(challenge)
        await db.commit()

        # Verify the challenge has difficulty_score attribute
        result = await db.get(Challenge, challenge.id)
        assert result is not None
        assert hasattr(result, 'difficulty_score')
        assert result.difficulty_score == 0.2  # default value