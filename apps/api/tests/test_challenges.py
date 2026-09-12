"""Integration tests for challenge CRUD and RBAC.

These run against the real PostgreSQL container. A dedicated engine + session
factory is created per test so asyncpg connections stay bound to the test's
event loop.
"""
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.flags import hash_flag, slugify
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, Challenge, User  # noqa: F401  (registers tables)

SessionFactory = async_sessionmaker[AsyncSession]


def _sysadmin(sub: str = "sysadmin-test") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["sysadmin"],
        permissions=["*"],
    )


def _faculty(sub: str = "faculty-test") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["faculty"],
        permissions=["challenge.view", "challenge.create", "challenge.edit", "challenge.publish"],
    )


def _student(sub: str = "student-test") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["student"],
        permissions=["challenge.view", "challenge.attempt"],
    )


@pytest.fixture
async def test_db():
    # Dedicated test database so tests never touch the running dev data.
    url = get_settings().database_url
    test_url = f"{url.rsplit('/', 1)[0]}/cyberlab_test"
    engine = create_async_engine(test_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _make_client(user: CurrentUser, factory: SessionFactory):
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
async def sysadmin_client(test_db):
    user = _sysadmin()
    await _ensure_user(test_db, user)
    async with _make_client(user, test_db) as client:
        yield client, user
    app.dependency_overrides.clear()


@pytest.fixture
async def faculty_client(test_db):
    user = _faculty()
    await _ensure_user(test_db, user)
    async with _make_client(user, test_db) as client:
        yield client, user
    app.dependency_overrides.clear()


@pytest.fixture
async def student_client(test_db):
    user = _student()
    await _ensure_user(test_db, user)
    async with _make_client(user, test_db) as client:
        yield client, user
    app.dependency_overrides.clear()


async def _seed_challenge(
    factory: SessionFactory, *, slug: str, status: str
) -> Challenge:
    async with factory() as db:
        existing = await db.scalar(select(Challenge).where(Challenge.slug == slug))
        if existing:
            return existing
        challenge = Challenge(
            slug=slug,
            title=f"Seed {slug}" if status == "published" else f"Draft {slug}",
            description=f"Description of {slug}",
            category="Linux" if status == "published" else "Web Security",
            difficulty="beginner" if status == "published" else "intermediate",
            points=100,
            flag_hash=hash_flag("IIC{seed}"),
            flag_format="IIC{...}",
            status=status,
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
async def test_student_sees_only_published(student_client, test_db):
    client, user = student_client
    pub = await _seed_challenge(
        test_db, slug=f"_test_pub_student_{uuid.uuid4().hex[:6]}", status="published"
    )
    draft = await _seed_challenge(
        test_db, slug=f"_test_draft_student_{uuid.uuid4().hex[:6]}", status="draft"
    )
    try:
        res = await client.get("/api/v1/challenges")
        assert res.status_code == 200
        slugs = [c["slug"] for c in res.json()]
        assert pub.slug in slugs
        assert draft.slug not in slugs
    finally:
        await _delete_by_slug(test_db, pub.slug)
        await _delete_by_slug(test_db, draft.slug)


@pytest.mark.asyncio
async def test_faculty_sees_drafts(faculty_client, test_db):
    client, user = faculty_client
    draft = await _seed_challenge(
        test_db, slug=f"_test_draft_faculty_{uuid.uuid4().hex[:6]}", status="draft"
    )
    try:
        res = await client.get("/api/v1/challenges")
        assert res.status_code == 200
        slugs = [c["slug"] for c in res.json()]
        assert draft.slug in slugs
    finally:
        await _delete_by_slug(test_db, draft.slug)


@pytest.mark.asyncio
async def test_student_cannot_create(student_client, test_db):
    client, user = student_client
    payload = {"title": "T", "description": "D", "category": "Linux", "difficulty": "beginner"}
    res = await client.post("/api/v1/challenges", json=payload)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_faculty_can_create(faculty_client, test_db):
    client, user = faculty_client
    slug = f"_test_create_{uuid.uuid4().hex[:6]}"
    try:
        payload = {
            "title": slug,
            "description": "Test challenge",
            "category": "Linux",
            "difficulty": "beginner",
            "points": 150,
            "flag": "IIC{test-flag}",
        }
        res = await client.post("/api/v1/challenges", json=payload)
        assert res.status_code == 201
        body = res.json()
        assert body["slug"] == slugify(slug)
        assert body["status"] == "draft"
        assert body["version"] == 1
    finally:
        await _delete_by_slug(test_db, slug)


@pytest.mark.asyncio
async def test_publish_challenge(sysadmin_client, test_db):
    client, user = sysadmin_client
    slug = f"_test_pub_{uuid.uuid4().hex[:6]}"
    try:
        res = await client.post(
            "/api/v1/challenges",
            json={
                "title": slug,
                "description": "Publish test",
                "category": "Linux",
                "difficulty": "beginner",
                "flag": "IIC{publish}",
            },
        )
        cid = res.json()["id"]
        res = await client.post(f"/api/v1/challenges/{cid}/publish")
        assert res.status_code == 200
        assert res.json()["status"] == "published"
        assert res.json()["version"] == 2
    finally:
        await _delete_by_slug(test_db, slug)


@pytest.mark.asyncio
async def test_publish_requires_flag(sysadmin_client, test_db):
    client, user = sysadmin_client
    slug = f"_test_noflag_{uuid.uuid4().hex[:6]}"
    try:
        res = await client.post(
            "/api/v1/challenges",
            json={
                "title": slug,
                "description": "No flag",
                "category": "Linux",
                "difficulty": "beginner",
            },
        )
        cid = res.json()["id"]
        res = await client.post(f"/api/v1/challenges/{cid}/publish")
        assert res.status_code == 400
    finally:
        await _delete_by_slug(test_db, slug)


@pytest.mark.asyncio
async def test_update_bumps_version(sysadmin_client, test_db):
    client, user = sysadmin_client
    slug = f"_test_bump_{uuid.uuid4().hex[:6]}"
    try:
        res = await client.post(
            "/api/v1/challenges",
            json={"title": slug, "description": "x", "category": "Linux", "difficulty": "beginner"},
        )
        cid = res.json()["id"]
        v1 = res.json()["version"]
        res = await client.patch(f"/api/v1/challenges/{cid}", json={"points": 999})
        assert res.status_code == 200
        assert res.json()["version"] == v1 + 1
        assert res.json()["points"] == 999
    finally:
        await _delete_by_slug(test_db, slug)


@pytest.mark.asyncio
async def test_delete_challenge(sysadmin_client, test_db):
    client, user = sysadmin_client
    slug = f"_test_del_{uuid.uuid4().hex[:6]}"
    try:
        res = await client.post(
            "/api/v1/challenges",
            json={"title": slug, "description": "x", "category": "Linux", "difficulty": "beginner"},
        )
        cid = res.json()["id"]
        res = await client.delete(f"/api/v1/challenges/{cid}")
        assert res.status_code == 204
    finally:
        await _delete_by_slug(test_db, slug)


def test_hash_flag():
    h = hash_flag("IIC{test}")
    assert isinstance(h, str)
    assert len(h) == 64
    assert h == hash_flag("  IIC{test}  ")