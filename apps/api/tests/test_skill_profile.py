import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.flags import hash_flag
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Challenge, User
from app.models.skill_profiles import UserSkillProfile
from app.models.skills import ChallengeSkill, Skill
from app.services.skill_profiles import update_profiles_for_solve

SessionFactory = async_sessionmaker[AsyncSession]

CORRECT = "IIC{test-flag}"

def _student(sub: str = "student-sub-test") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["student"],
        permissions=["challenge.view", "submission.create"],
    )


def _make_client(factory: SessionFactory, user: CurrentUser | None = None):
    async def _db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session
    app.dependency_overrides[get_db] = _db
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

async def _ensure_user(factory: SessionFactory, user: CurrentUser) -> None:
    async with factory() as db:
        if await db.get(User, user.id) is None:
            db.add(User(id=user.id, keycloak_sub=user.keycloak_sub, email=f"{user.keycloak_sub}@cyberlab.test", display_name="Test Student"))
            await db.commit()

