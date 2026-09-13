"""Integration tests for API rate limiting (PRD §51)."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.flags import hash_flag
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Challenge, User  # noqa: F401  (registers tables)

SessionFactory = async_sessionmaker[AsyncSession]

CORRECT = "IIC{test-flag}"


def _student(sub: str) -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["student"],
        permissions=["challenge.view", "challenge.attempt", "submission.create"],
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


def _make_client(factory: SessionFactory, user: CurrentUser):
    async def _db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _ensure_user(factory: SessionFactory, user: CurrentUser) -> None:
    async with factory() as db:
        existing = await db.get(User, user.id)
        if existing is None:
            db.add(
                User(
                    id=user.id,
                    keycloak_sub=user.keycloak_sub,
                    email=f"{user.keycloak_sub}@cyberlab.test",
                    display_name=f"Test {user.roles[0].title()}",
                )
            )
            await db.commit()


async def _seed_challenge(factory: SessionFactory, *, slug: str, points: int) -> Challenge:
    async with factory() as db:
        challenge = Challenge(
            slug=slug,
            title=f"Seed {slug}",
            description=f"Description of {slug}",
            category="Linux",
            difficulty="beginner",
            points=points,
            flag_hash=hash_flag(CORRECT),
            flag_format="IIC{...}",
            status="published",
        )
        db.add(challenge)
        await db.commit()
        await db.refresh(challenge)
        return challenge


@pytest.mark.asyncio
async def test_flag_submission_triggers_429_after_limit(test_db):
    user = _student(sub=f"rl-submit-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenge = await _seed_challenge(test_db, slug=f"_rl_{uuid.uuid4().hex[:6]}", points=50)
    async with _make_client(test_db, user) as client:
        for i in range(10):
            res = await client.post(
                f"/api/v1/challenges/{challenge.id}/submissions",
                json={"flag": f"IIC{{wrong-{i}}}"},
            )
            assert res.status_code == 201
        res = await client.post(
            f"/api/v1/challenges/{challenge.id}/submissions",
            json={"flag": "IIC{wrong-11}"},
        )
        assert res.status_code == 429
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_hint_reveal_triggers_429_after_limit(test_db):
    user = _student(sub=f"rl-hint-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenge = await _seed_challenge(test_db, slug=f"_rh_{uuid.uuid4().hex[:6]}", points=50)
    async with _make_client(test_db, user) as client:
        for _i in range(20):
            res = await client.post(
                f"/api/v1/challenges/{challenge.id}/hints/0/reveal",
            )
            assert res.status_code != 429
        res = await client.post(
            f"/api/v1/challenges/{challenge.id}/hints/0/reveal",
        )
        assert res.status_code == 429
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rate_limit_is_per_user(test_db):
    """A second user is not affected by another user's exhausted bucket."""
    user_a = _student(sub=f"rl-a-{uuid.uuid4().hex[:6]}")
    user_b = _student(sub=f"rl-b-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user_a)
    await _ensure_user(test_db, user_b)
    challenge = await _seed_challenge(test_db, slug=f"_rp_{uuid.uuid4().hex[:6]}", points=50)

    async with _make_client(test_db, user_a) as client:
        for i in range(10):
            await client.post(
                f"/api/v1/challenges/{challenge.id}/submissions",
                json={"flag": f"IIC{{wrong-{i}}}"},
            )
        res = await client.post(
            f"/api/v1/challenges/{challenge.id}/submissions",
            json={"flag": "IIC{wrong-11}"},
        )
        assert res.status_code == 429
    app.dependency_overrides.clear()

    async with _make_client(test_db, user_b) as client:
        res = await client.post(
            f"/api/v1/challenges/{challenge.id}/submissions",
            json={"flag": "IIC{wrong-b}"},
        )
        assert res.status_code == 201
    app.dependency_overrides.clear()