"""Unit and integration tests for Phase 5 Adaptive Learning models."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.models import Challenge, User
from app.models.learning_paths import LearningPath, LearningPathStep
from app.models.skill_profiles import UserSkillProfile


@pytest.fixture
async def test_db():
    url = get_settings().database_url
    test_url = f"{url.rsplit('/', 1)[0]}/cyberlab_test"
    engine = create_async_engine(test_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_adaptive_tables_exist(test_db):
    """Test that new metadata objects are registered and tables exist."""
    async with test_db() as db:
        assert await db.scalar(select(LearningPath).limit(1)) is None
        assert await db.scalar(select(LearningPathStep).limit(1)) is None
        assert await db.scalar(select(UserSkillProfile).limit(1)) is None
