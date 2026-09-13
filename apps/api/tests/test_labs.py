"""Integration tests for lab lifecycle (Phase 2 Cyber Range, PRD §46-§51)."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.flags import hash_flag
from app.db.base import Base
from app.db.session import get_db
from app.infrastructure import docker as docker_module
from app.infrastructure.docker import DockerError
from app.main import app
from app.models import Challenge, User  # noqa: F401  (registers tables)

SessionFactory = async_sessionmaker[AsyncSession]

CORRECT = "IIC{test-flag}"


def _student(sub: str) -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["student"],
        permissions=["challenge.view", "challenge.attempt", "lab.launch", "lab.reset"],
    )


def _other_user(sub: str, roles: list[str]) -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=roles,
        permissions=["lab.launch", "lab.reset"],
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


async def _seed_challenge(
    factory: SessionFactory, *, slug: str, environment_type: str = "static"
) -> Challenge:
    async with factory() as db:
        challenge = Challenge(
            slug=slug,
            title=f"Seed {slug}",
            description=f"Description of {slug}",
            category="Linux",
            difficulty="beginner",
            points=50,
            flag_hash=hash_flag(CORRECT),
            flag_format="IIC{...}",
            status="published",
            environment_type=environment_type,
        )
        db.add(challenge)
        await db.commit()
        await db.refresh(challenge)
        return challenge


HOST_ID = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


@pytest.fixture(autouse=True)
def fake_docker(monkeypatch):
    """Replace the docker adapter with in-memory behaviour."""

    async def ensure_network(name: str) -> None:
        pass

    async def create_and_start_container(
        name: str, image: str, network: str, cmd: list[str] | None = None
    ) -> tuple[str, str]:
        return HOST_ID, "172.30.0.10"

    async def stop_container(container_id: str) -> None:
        if container_id is None:
            raise DockerError("missing id")

    async def remove_container(container_id: str) -> None:
        pass

    monkeypatch.setattr(docker_module, "ensure_network", ensure_network)
    monkeypatch.setattr(docker_module, "create_and_start_container", create_and_start_container)
    monkeypatch.setattr(docker_module, "stop_container", stop_container)
    monkeypatch.setattr(docker_module, "remove_container", remove_container)


async def test_launch_requires_lab_environment(test_db):
    user = _student(sub=f"lab-none-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenge = await _seed_challenge(
        test_db, slug=f"_ln_{uuid.uuid4().hex[:6]}", environment_type="none"
    )
    async with _make_client(test_db, user) as client:
        res = await client.post(f"/api/v1/challenges/{challenge.id}/lab/launch")
    assert res.status_code == 400
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_launch_creates_running_lab(test_db):
    user = _student(sub=f"lab-launch-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenge = await _seed_challenge(test_db, slug=f"_ll_{uuid.uuid4().hex[:6]}")
    async with _make_client(test_db, user) as client:
        res = await client.post(f"/api/v1/challenges/{challenge.id}/lab/launch")
        assert res.status_code == 201
        lab = res.json()
        assert lab["status"] == "running"
        assert lab["challenge_title"] == f"Seed {challenge.slug}"
        assert lab["connection_hint"] is not None
        assert lab["expires_at"] is not None
        res = await client.get("/api/v1/labs")
        assert res.status_code == 200
        assert len(res.json()) == 1
    app.dependency_overrides.clear()


async def test_quota_limits_concurrent_labs(test_db):
    user = _student(sub=f"lab-quota-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenges = [
        await _seed_challenge(test_db, slug=f"_lq_{uuid.uuid4().hex[:6]}")
        for _ in range(3)
    ]
    async with _make_client(test_db, user) as client:
        for challenge in challenges[:2]:
            res = await client.post(f"/api/v1/challenges/{challenge.id}/lab/launch")
            assert res.status_code == 201
        res = await client.post(f"/api/v1/challenges/{challenges[2].id}/lab/launch")
        assert res.status_code == 409
    app.dependency_overrides.clear()


async def test_stop_and_reset_flow(test_db):
    user = _student(sub=f"lab-stop-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenge = await _seed_challenge(test_db, slug=f"_ls_{uuid.uuid4().hex[:6]}")
    async with _make_client(test_db, user) as client:
        lab = (
            await client.post(f"/api/v1/challenges/{challenge.id}/lab/launch")
        ).json()
        res = await client.post(f"/api/v1/labs/{lab['id']}/stop")
        assert res.status_code == 200
        assert res.json()["status"] == "stopped"

        res = await client.post(f"/api/v1/labs/{lab['id']}/reset")
        assert res.status_code == 200
        assert res.json()["status"] == "running"
        assert res.json()["expires_at"] is not None
    app.dependency_overrides.clear()


async def test_expire_flow(test_db):
    user = _student(sub=f"lab-expire-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenge = await _seed_challenge(test_db, slug=f"_le_{uuid.uuid4().hex[:6]}")
    async with _make_client(test_db, user) as client:
        lab = (
            await client.post(f"/api/v1/challenges/{challenge.id}/lab/launch")
        ).json()
        res = await client.post(f"/api/v1/labs/{lab['id']}/expire")
        assert res.status_code == 200
        assert res.json()["status"] == "expired"
    app.dependency_overrides.clear()


async def test_cannot_manage_someone_elses_lab(test_db):
    owner = _student(sub=f"lab-owner-{uuid.uuid4().hex[:6]}")
    other = _other_user(sub=f"lab-other-{uuid.uuid4().hex[:6]}", roles=["student"])
    await _ensure_user(test_db, owner)
    await _ensure_user(test_db, other)
    challenge = await _seed_challenge(test_db, slug=f"_lo_{uuid.uuid4().hex[:6]}")

    async with _make_client(test_db, owner) as client:
        lab = (
            await client.post(f"/api/v1/challenges/{challenge.id}/lab/launch")
        ).json()
    app.dependency_overrides.clear()

    async with _make_client(test_db, other) as client:
        res = await client.post(f"/api/v1/labs/{lab['id']}/stop")
    assert res.status_code == 403
    app.dependency_overrides.clear()


async def test_launch_returns_503_on_docker_failure(test_db, monkeypatch):
    async def boom(*args, **kwargs):
        raise DockerError("daemon unreachable")

    monkeypatch.setattr(docker_module, "create_and_start_container", boom)
    user = _student(sub=f"lab-503-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenge = await _seed_challenge(test_db, slug=f"_l5_{uuid.uuid4().hex[:6]}")
    async with _make_client(test_db, user) as client:
        res = await client.post(f"/api/v1/challenges/{challenge.id}/lab/launch")
        assert res.status_code == 503
        assert "unavailable" in res.json()["detail"]
    app.dependency_overrides.clear()


async def test_launch_returns_503_on_unexpected_failure(test_db, monkeypatch):
    async def boom(*args, **kwargs):
        raise ValueError("adapter bug")

    monkeypatch.setattr(docker_module, "create_and_start_container", boom)
    user = _student(sub=f"lab-bug-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenge = await _seed_challenge(test_db, slug=f"_lb_{uuid.uuid4().hex[:6]}")
    async with _make_client(test_db, user) as client:
        res = await client.post(f"/api/v1/challenges/{challenge.id}/lab/launch")
        assert res.status_code == 503
        assert "unexpected error" in res.json()["detail"]
        res = await client.get("/api/v1/labs")
        assert res.json()[0]["status"] == "error"
        assert "adapter bug" in res.json()[0]["error_message"]
    app.dependency_overrides.clear()


async def test_lazy_expiry_marks_overdue_running_lab(test_db):
    user = _student(sub=f"lab-lazy-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenge = await _seed_challenge(test_db, slug=f"_ly_{uuid.uuid4().hex[:6]}")
    async with _make_client(test_db, user) as client:
        lab = (
            await client.post(f"/api/v1/challenges/{challenge.id}/lab/launch")
        ).json()
        lab_id = lab["id"]
    app.dependency_overrides.clear()

    from app.models.labs import LabInstance

    async with test_db() as session:
        row = await session.get(LabInstance, uuid.UUID(lab_id))
        row.expires_at = datetime.now(UTC).replace(microsecond=0)
        await session.commit()

    async with _make_client(test_db, user) as client:
        res = await client.get("/api/v1/labs")
        assert res.status_code == 200
        assert res.json()[0]["status"] == "expired"
    app.dependency_overrides.clear()