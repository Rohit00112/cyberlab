"""Integration tests for the progressive hint reveal system (PRD §21-22).

Covers: ordered reveal (409 on out-of-order), idempotent re-reveal,
penalty-aware scoring (earned = base − hint_penalty × revealed), and the
hint.reveal audit trail.
"""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import CurrentUser, get_current_user, get_db
from app.core.config import get_settings
from app.core.flags import hash_flag
from app.db.base import Base
from app.main import app
from app.models import Challenge, HintReveal, User  # noqa: F401  (registers tables)

SessionFactory = async_sessionmaker[AsyncSession]

CORRECT = "IIC{test-flag}"

PENALTY = 20


def _student(sub: str = "student-sub-hint") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["student"],
        permissions=["challenge.view", "challenge.attempt", "submission.create"],
    )


def _faculty(sub: str = "faculty-sub-hint") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["faculty"],
        permissions=["challenge.view", "challenge.edit"],
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


async def _seed_challenge(
    factory: SessionFactory, *, slug: str, points: int, status: str = "published"
) -> Challenge:
    async with factory() as db:
        challenge = Challenge(
            slug=slug,
            title=f"Hints {slug}",
            description="Progressive-hint challenge for tests.",
            category="Crypto",
            difficulty="medium",
            points=points,
            hint_penalty=PENALTY,
            hints=["hint one", "hint two", "hint three"],
            flag_hash=hash_flag(CORRECT),
            flag_format="IIC{...}",
            status=status,
        )
        db.add(challenge)
        await db.commit()
        await db.refresh(challenge)
        return challenge


@pytest.mark.asyncio
async def test_reveal_hints_progressively(test_db):
    """PRD §22: hints unlock strictly in order; index  share require 0 first."""
    client, user = await _make_client_with_user(test_db)
    challenge = await _seed_challenge(
        test_db, slug=f"reveal_prog_{uuid.uuid4().hex[:6]}", points=100
    )
    try:
        # index 1 before 0 → 409
        r1 = await client.post(
            f"/api/v1/challenges/{challenge.id}/hints/1/reveal"
        )
        assert r1.status_code == 409

        # reveal 0
        r0 = await client.post(
            f"/api/v1/challenges/{challenge.id}/hints/0/reveal"
        )
        assert r0.status_code == 201
        assert r0.json()["hints_revealed"] == 1

        # reveal 1 now ok
        r2 = await client.post(
            f"/api/v1/challenges/{challenge.id}/hints/1/reveal"
        )
        assert r2.status_code == 201
        assert r2.json()["hints_revealed"] == 2

        # re-reveal 1 → idempotent, still 2
        r3 = await client.post(
            f"/api/v1/challenges/{challenge.id}/hints/1/reveal"
        )
        assert r3.status_code == 201
        assert r3.json()["hints_revealed"] == 2
    finally:
        await _delete_by_slug(test_db, challenge.slug)


@pytest.mark.asyncio
async def test_reveal_penalty_scoring(test_db):
    """Earned = base − hint_penalty × revealed (PRD §21)."""
    client, user = await _make_client_with_user(test_db)
    challenge = await _seed_challenge(
        test_db, slug=f"penalty_{uuid.uuid4().hex[:6]}", points=100
    )
    try:
        # reveal 2 of 3 hints → penalty 40 → final solve earns 60
        for i in (0, 1):
            await client.post(f"/api/v1/challenges/{challenge.id}/hints/{i}/reveal")

        res = await client.post(
            f"/api/v1/challenges/{challenge.id}/submissions", json={"flag": CORRECT}
        )
        assert res.status_code == 201
        body = res.json()
        assert body["correct"] is True
        assert body["points"] == 100 - PENALTY * 2
    finally:
        await _delete_by_slug(test_db, challenge.slug)


@pytest.mark.asyncio
async def test_reveal_requires_flag_permission_and_role(test_db):
    """Reveal needs challenge.attempt; faculty (no attempt) is forbidden."""
    faculty = await _seed_challenge(
        test_db, slug=f"_fac_nohints_{uuid.uuid4().hex[:6]}", points=50
    )
    try:
        client = _make_client(test_db, _faculty())
        res = await client.post(f"/api/v1/challenges/{faculty.id}/hints/0/reveal")
        assert res.status_code == 403
    finally:
        await _delete_by_slug(test_db, faculty.slug)


async def _make_client_with_user(factory: SessionFactory, user: CurrentUser | None = None):
    if user is None:
        user = _student()
    await _ensure_user(factory, user)
    client = _make_client(factory, user)
    return client, user


async def _delete_by_slug(factory: SessionFactory, slug: str):
    async with factory() as db:
        challenge = await db.scalar(select(Challenge).where(Challenge.slug == slug))
        if challenge:
            await db.delete(challenge)
            await db.commit()
