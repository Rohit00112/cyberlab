"""Integration tests for the user profile endpoint."""

from __future__ import annotations

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
from app.models import Challenge, Submission, User  # noqa: F401  (registers tables)

SessionFactory = async_sessionmaker[AsyncSession]

CORRECT = "IIC{profile-flag}"


def _student(sub: str = "profile-student") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["student"],
        permissions=["challenge.view", "submission.create"],
    )


def _sysadmin(sub: str = "profile-sysadmin") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["sysadmin"],
        permissions=["*"],
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


async def _ensure_user(
    factory: SessionFactory, user: CurrentUser, *, roles: list[str] | None = None
) -> None:
    async with factory() as db:
        existing = await db.get(User, user.id)
        if existing is None:
            db.add(
                User(
                    id=user.id,
                    keycloak_sub=user.keycloak_sub,
                    email=f"{user.keycloak_sub}@cyberlab.test",
                    display_name=f"Test {user.roles[0].title()}",
                    roles=roles if roles is not None else user.roles,
                )
            )
            await db.commit()


async def _seed_challenge(
    factory: SessionFactory, *, slug: str, points: int, skills: list[str]
) -> Challenge:
    async with factory() as db:
        challenge = Challenge(
            slug=slug,
            title=f"Seed {slug}",
            description=f"Description of {slug}",
            category="Linux",
            difficulty="beginner",
            points=points,
            skills=skills,
            flag_hash=hash_flag(CORRECT),
            flag_format="IIC{...}",
            status="published",
        )
        db.add(challenge)
        await db.commit()
        await db.refresh(challenge)
        return challenge


async def _delete_by_slug(factory: SessionFactory, slug: str):
    async with factory() as db:
        challenge = await db.scalar(select(Challenge).where(Challenge.slug == slug))
        if challenge:
            await db.delete(challenge)
            await db.commit()


@pytest.mark.asyncio
async def test_profile_empty_for_new_user(test_db):
    user = _student()
    await _ensure_user(test_db, user)
    async with _make_client(test_db, user) as client:
        res = await client.get("/api/v1/users/me")
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == str(user.id)
        assert body["display_name"] == "Test Student"
        assert body["roles"] == ["student"]
        assert body["points"] == 0
        assert body["solved_count"] == 0
        assert body["attempts"] == 0
        assert body["recent_solves"] == []
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_profile_reflects_solves(test_db):
    user = _student()
    await _ensure_user(test_db, user)
    challenge = await _seed_challenge(
        test_db, slug=f"_prof_{uuid.uuid4().hex[:6]}", points=150, skills=["ssh", "nmap"]
    )
    try:
        async with _make_client(test_db, user) as client:
            await client.post(
                f"/api/v1/challenges/{challenge.id}/submissions", json={"flag": CORRECT}
            )
            res = await client.get("/api/v1/users/me")
            assert res.status_code == 200
            body = res.json()
            assert body["points"] == 150
            assert body["solved_count"] == 1
            assert body["attempts"] == 1
            assert len(body["recent_solves"]) == 1
            solve = body["recent_solves"][0]
            assert solve["challenge_id"] == str(challenge.id)
            assert solve["title"] == f"Seed {challenge.slug}"
            assert solve["points"] == 150
            assert solve["skills"] == ["ssh", "nmap"]
            assert solve["solved_at"]
    finally:
        await _delete_by_slug(test_db, challenge.slug)
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_profile_requires_auth(test_db):
    async with _make_client(test_db) as client:
        res = await client.get("/api/v1/users/me")
        assert res.status_code == 401
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_lists_users(test_db):
    admin = _sysadmin()
    target = _student(sub=f"target-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, admin)
    await _ensure_user(test_db, target)
    async with _make_client(test_db, admin) as client:
        res = await client.get("/api/v1/users")
        assert res.status_code == 200
        body = res.json()
        assert any(u["id"] == str(target.id) for u in body)
        row = next(u for u in body if u["id"] == str(target.id))
        assert row["roles"] == ["student"]
        assert row["is_active"] is True
        assert row["points"] == 0
        assert row["solved_count"] == 0
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_suspend_activate(test_db):
    admin = _sysadmin()
    target = _student(sub=f"suspend-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, admin)
    await _ensure_user(test_db, target)
    async with _make_client(test_db, admin) as client:
        res = await client.patch(f"/api/v1/users/{target.id}", json={"is_active": False})
        assert res.status_code == 200
        assert res.json()["is_active"] is False

        res = await client.patch(f"/api/v1/users/{target.id}", json={"is_active": True})
        assert res.status_code == 200
        assert res.json()["is_active"] is True
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_suspended_user_forbidden(test_db, monkeypatch):
    admin = _sysadmin()
    target = _student(sub=f"blocked-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, admin)
    await _ensure_user(test_db, target)
    async with _make_client(test_db, admin) as client:
        await client.patch(f"/api/v1/users/{target.id}", json={"is_active": False})
    app.dependency_overrides.clear()

    # Exercise the real get_current_user dependency path: fake OIDC decode but
    # keep the suspension check, by calling the dependency directly.
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    import app.api.deps as deps_module

    async def _fake_decode(token):
        assert token == "blocked-token"
        return {"sub": target.keycloak_sub, "realm_access": {"roles": ["student"]}}

    monkeypatch.setattr(deps_module.oidc, "decode_token", _fake_decode)

    async with test_db() as db:
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="blocked-token")
        with pytest.raises(HTTPException) as excinfo:
            await deps_module.get_current_user(creds, db)
        assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_student_cannot_access_directory(test_db):
    student = _student(sub=f"nosys-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, student)
    async with _make_client(test_db, student) as client:
        res = await client.get("/api/v1/users")
        assert res.status_code == 403
    app.dependency_overrides.clear()
