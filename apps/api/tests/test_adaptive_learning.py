"""Unit and integration tests for Phase 5 Adaptive Learning models."""


import pytest
from sqlalchemy import select

from app.models.learning_paths import LearningPath, LearningPathStep
from app.models.skill_profiles import UserSkillProfile


@pytest.mark.asyncio
async def test_adaptive_tables_exist(test_db):
    """Test that new metadata objects are registered and tables exist."""
    async with test_db() as db:
        assert await db.scalar(select(LearningPath).limit(1)) is None
        assert await db.scalar(select(LearningPathStep).limit(1)) is None
        assert await db.scalar(select(UserSkillProfile).limit(1)) is None
