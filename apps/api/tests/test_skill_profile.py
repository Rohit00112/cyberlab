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

@pytest.fixture
async def student_client(test_db):
    user = _student()
    await _ensure_user(test_db, user)
    async with _make_client(test_db, user) as client:
        yield client, user
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_correct_solve_creates_profile(student_client, test_db):
    client, user = student_client
    async with test_db() as db:
        skill = Skill(slug="test-skill", name="Test Skill", is_active=True)
        db.add(skill)
        await db.commit()
        await db.refresh(skill)

        challenge = Challenge(
            slug=f"_t_{uuid.uuid4().hex[:6]}",
            title="Test Challenge",
            description="Test DB",
            category="Linux",
            difficulty="advanced",
            points=100,
            difficulty_score=0.8,
            flag_hash=hash_flag(CORRECT),
            flag_format="IIC{...}",
            status="published",
        )
        db.add(challenge)
        await db.commit()
        await db.refresh(challenge)
        db.add(ChallengeSkill(challenge_id=challenge.id, skill_id=skill.id))
        await db.commit()

    res = await client.post(f"/api/v1/challenges/{challenge.id}/submissions", json={"flag": CORRECT})
    assert res.status_code == 201
    assert res.json()["correct"] is True

    # Assert profile
    async with test_db() as db:
        profile = await db.scalar(select(UserSkillProfile).where(UserSkillProfile.user_id == user.id))
        assert profile is not None
        assert profile.skill_id == skill.id
        assert profile.competency_level == 8.0

@pytest.mark.asyncio
async def test_competency_never_exceeds_100(test_db):
    user_id = uuid.uuid4()
    skill_id = uuid.uuid4()

    async with test_db() as db:
        user = User(id=user_id, keycloak_sub="t2", email="t2@cy.test", display_name="T2")
        skill = Skill(id=skill_id, slug="t2-skill", name="T2 Skill")
        db.add_all([user, skill])
        await db.flush()

        profil = UserSkillProfile(user_id=user.id, skill_id=skill.id, competency_level=96.0)
        db.add(profil)
        await db.commit()

        challenge = Challenge(
            slug=f"t2_{uuid.uuid4().hex[:6]}",
            title="T2",
            description="T2",
            category="Linux",
            difficulty="advanced",
            points=100,
            difficulty_score=0.8,
            flag_hash=hash_flag(CORRECT),
            flag_format="IIC{...}",
            status="published",
        )
        db.add(challenge)
        await db.commit()
        await db.refresh(challenge)
        db.add(ChallengeSkill(challenge_id=challenge.id, skill_id=skill.id))
        await db.commit()

        await update_profiles_for_solve(db, user_id=user.id, challenge=challenge)
        await db.commit()

        p2 = await db.scalar(select(UserSkillProfile).where(UserSkillProfile.user_id == user_id))
        assert p2.competency_level == 100.0
