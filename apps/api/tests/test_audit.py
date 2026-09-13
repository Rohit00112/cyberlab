"""Integration tests for audit log review (PRD §51, §54 Security)."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import CurrentUser, get_current_user
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import User  # noqa: F401  (registers tables)

SessionFactory = async_sessionmaker[AsyncSession]


def _faculty(sub: str = "faculty-audit-test") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["faculty"],
        permissions=["challenge.view", "challenge.create", "audit.view"],
    )


def _student(sub: str = "student-audit-test") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["student"],
        permissions=["challenge.view"],
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


@pytest.fixture
async def faculty_client(test_db):
    user = _faculty(sub=f"faculty-audit-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    async with _make_client(test_db, user) as client:
        yield client, user
    app.dependency_overrides.clear()


async def test_audit_rejected_for_student(test_db):
    user = _student(sub=f"student-audit-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    async with _make_client(test_db, user) as client:
        res = await client.get("/api/v1/audit/logs")
    assert res.status_code == 403
    app.dependency_overrides.clear()


async def test_audit_rejected_for_anonymous(test_db):
    async def _db() -> AsyncIterator[AsyncSession]:
        async with test_db() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/audit/logs")
    assert res.status_code == 401
    app.dependency_overrides.clear()


async def test_audit_lists_challenge_create_event(faculty_client):
    client, faculty = faculty_client
    slug = f"audit{uuid.uuid4().hex[:6]}"
    res = await client.post(
        "/api/v1/challenges",
        json={
            "title": f"Audit seed {slug}",
            "description": "created by audit test",
            "category": "Linux",
            "difficulty": "beginner",
            "points": 10,
            "flag": "IIC{audit}",
            "status": "draft",
        },
    )
    assert res.status_code == 201

    res = await client.get("/api/v1/audit/logs")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) >= 1
    assert rows[0]["event"] == "challenge.create"
    assert rows[0]["target_id"] == f"audit-seed-{slug}"
    assert rows[0]["user_id"] == str(faculty.id)
    assert rows[0]["display_name"] == "Test Faculty"


async def test_audit_event_filter(faculty_client):
    client, _ = faculty_client
    slug = f"audit{uuid.uuid4().hex[:6]}"
    await client.post(
        "/api/v1/challenges",
        json={
            "title": f"Audit seed {slug}",
            "description": "created by audit test",
            "category": "Linux",
            "difficulty": "beginner",
            "points": 10,
            "flag": "IIC{audit}",
            "status": "draft",
        },
    )
    res = await client.get("/api/v1/audit/logs", params={"event": "challenge.publish"})
    assert res.status_code == 200
    rows = res.json()
    assert all(row["event"] == "challenge.publish" for row in rows)

    res = await client.get("/api/v1/audit/logs", params={"event": "challenge.create"})
    assert res.status_code == 200
    assert any(row["target_id"] == f"audit-seed-{slug}" for row in res.json())


async def test_audit_respects_pagination(faculty_client):
    client, _ = faculty_client
    for i in range(3):
        await client.post(
            "/api/v1/challenges",
            json={
                "title": f"Audit page {i} {uuid.uuid4().hex[:4]}",
                "description": "created by audit test",
                "category": "Linux",
                "difficulty": "beginner",
                "points": 10,
                "flag": "IIC{audit}",
                "status": "draft",
            },
        )
    res = await client.get("/api/v1/audit/logs", params={"limit": 2, "offset": 1})
    assert res.status_code == 200
    assert len(res.json()) == 2