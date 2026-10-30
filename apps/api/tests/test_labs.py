"""Integration tests for lab lifecycle (Phase 2 Cyber Range, PRD §46-§51)."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import CurrentUser, get_current_user
from app.core import rust_engine
from app.core.config import get_settings
from app.core.flags import hash_flag
from app.db.base import Base
from app.db.session import get_db
from app.infrastructure import docker as docker_module
from app.infrastructure.docker import DockerError
from app.main import app
from app.models import Challenge, User  # noqa: F401  (registers tables)
from app.models.audit_logs import AuditLog
from app.models.labs import LabInstance
from app.models.provisioning import ProvisioningJob
from app.services import labs as lab_service

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


async def test_concurrent_async_launch_has_one_lab_and_durable_job(test_db, monkeypatch):
    from app.tasks.provisioning import provision_lab_task

    user = _student(sub=f"lab-concurrent-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenge = await _seed_challenge(
        test_db, slug=f"_lc_{uuid.uuid4().hex[:6]}"
    )
    monkeypatch.setattr(
        provision_lab_task, "delay", lambda job_id: SimpleNamespace(id=f"queued-{job_id}")
    )

    async def launch():
        async with test_db() as db:
            return await lab_service.launch_lab(db, user, challenge, sync=False)

    first, second = await asyncio.gather(launch(), launch())
    assert first.id == second.id
    assert first.job_id == second.job_id
    assert first.job_id is not None
    async with test_db() as db:
        assert await db.scalar(select(func.count()).select_from(LabInstance)) == 1
        assert await db.scalar(select(func.count()).select_from(ProvisioningJob)) == 1


async def test_concurrent_async_launch_respects_user_quota(test_db, monkeypatch):
    from app.tasks.provisioning import provision_lab_task

    user = _student(sub=f"lab-concurrent-quota-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenges = [
        await _seed_challenge(test_db, slug=f"_lcq_{uuid.uuid4().hex[:6]}")
        for _ in range(3)
    ]
    monkeypatch.setattr(
        provision_lab_task, "delay", lambda job_id: SimpleNamespace(id=f"queued-{job_id}")
    )

    async def launch(challenge):
        async with test_db() as db:
            return await lab_service.launch_lab(db, user, challenge, sync=False)

    results = await asyncio.gather(
        *(launch(challenge) for challenge in challenges), return_exceptions=True
    )
    successful = [result for result in results if not isinstance(result, BaseException)]
    rejected = [result for result in results if isinstance(result, HTTPException)]
    assert len(successful) == 2
    assert len(rejected) == 1 and rejected[0].status_code == 409
    async with test_db() as db:
        assert await db.scalar(select(func.count()).select_from(LabInstance)) == 2
        assert await db.scalar(select(func.count()).select_from(ProvisioningJob)) == 2


async def test_failed_broker_dispatch_is_durable_and_retried(test_db, monkeypatch):
    from app.tasks import provisioning

    user = _student(sub=f"lab-retry-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenge = await _seed_challenge(test_db, slug=f"_lr_{uuid.uuid4().hex[:6]}")

    def broker_down(_job_id):
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr(provisioning.provision_lab_task, "delay", broker_down)
    async with test_db() as db:
        queued = await lab_service.launch_lab(db, user, challenge, sync=False)
    assert queued.status == "queued" and queued.job_id is not None
    async with test_db() as db:
        job = await db.get(ProvisioningJob, queued.job_id)
        assert job.status == "pending" and job.celery_task_id is None

    monkeypatch.setattr(provisioning, "SessionLocal", test_db)
    monkeypatch.setattr(
        provisioning.provision_lab_task,
        "delay",
        lambda job_id: SimpleNamespace(id=f"replayed-{job_id}"),
    )
    assert await provisioning.redispatch_pending_provisioning_jobs() == 1
    async with test_db() as db:
        job = await db.get(ProvisioningJob, queued.job_id)
        assert job.status == "pending"
        assert job.celery_task_id == f"replayed-{queued.job_id}"


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
        assert res.json()[0]["status"] == "failed"
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


_LAST_FLAG = {}


@pytest.fixture
def capture_flag_cmd(monkeypatch):
    """Capture the per-session flag injected into each container command."""
    _LAST_FLAG.clear()

    async def create_and_start_container(
        name: str, image: str, network: str, cmd: list[str] | None = None
    ) -> tuple[str, str]:
        _LAST_FLAG["flag"] = cmd[2].split("'")[3] if cmd else None
        return HOST_ID, "172.30.0.10"

    monkeypatch.setattr(
        docker_module, "create_and_start_container", create_and_start_container
    )


def _flag_submitter(sub: str) -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["student"],
        permissions=["challenge.view", "challenge.attempt", "lab.launch", "submission.create"],
    )


async def test_submit_with_running_lab_flag(test_db, capture_flag_cmd):
    user = _flag_submitter(sub=f"lab-flag-ok-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenge = await _seed_challenge(test_db, slug=f"_lf_{uuid.uuid4().hex[:6]}")

    async with _make_client(test_db, user) as client:
        lab = (
            await client.post(f"/api/v1/challenges/{challenge.id}/lab/launch")
        ).json()
        assert lab["status"] == "running"
        assert _LAST_FLAG["flag"].startswith("IIC{lab-")

        res = await client.post(
            f"/api/v1/challenges/{challenge.id}/submissions",
            json={"flag": _LAST_FLAG["flag"], "lab_id": lab["id"]},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["correct"] is True
        assert body["points"] == 50
    app.dependency_overrides.clear()


async def test_submit_static_flag_fails_when_lab_id_given(test_db, capture_flag_cmd):
    user = _flag_submitter(sub=f"lab-flag-mix-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenge = await _seed_challenge(test_db, slug=f"_lfx_{uuid.uuid4().hex[:6]}")

    async with _make_client(test_db, user) as client:
        lab = (
            await client.post(f"/api/v1/challenges/{challenge.id}/lab/launch")
        ).json()
        res = await client.post(
            f"/api/v1/challenges/{challenge.id}/submissions",
            json={"flag": CORRECT, "lab_id": lab["id"]},
        )
        assert res.status_code == 201
        assert res.json()["correct"] is False
    app.dependency_overrides.clear()


async def test_submit_with_lab_id_mismatched_challenge(test_db, capture_flag_cmd):
    user = _flag_submitter(sub=f"lab-flag-mism-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenge_a = await _seed_challenge(test_db, slug=f"_lfa_{uuid.uuid4().hex[:6]}")
    challenge_b = await _seed_challenge(test_db, slug=f"_lfb_{uuid.uuid4().hex[:6]}")

    async with _make_client(test_db, user) as client:
        lab = (
            await client.post(f"/api/v1/challenges/{challenge_a.id}/lab/launch")
        ).json()
        res = await client.post(
            f"/api/v1/challenges/{challenge_b.id}/submissions",
            json={"flag": CORRECT, "lab_id": lab["id"]},
        )
        assert res.status_code == 400
    app.dependency_overrides.clear()


async def test_submit_with_stopped_lab_rejected(test_db, capture_flag_cmd):
    user = _flag_submitter(sub=f"lab-flag-stop-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenge = await _seed_challenge(test_db, slug=f"_lfs_{uuid.uuid4().hex[:6]}")

    async with _make_client(test_db, user) as client:
        lab = (
            await client.post(f"/api/v1/challenges/{challenge.id}/lab/launch")
        ).json()
        await client.post(f"/api/v1/labs/{lab['id']}/stop")
        res = await client.post(
            f"/api/v1/challenges/{challenge.id}/submissions",
            json={"flag": CORRECT, "lab_id": lab["id"]},
        )
        assert res.status_code == 409
    app.dependency_overrides.clear()


async def test_submit_with_someone_elses_lab_rejected(test_db, capture_flag_cmd):
    owner = _flag_submitter(sub=f"lab-flag-owner-{uuid.uuid4().hex[:6]}")
    intruder = _flag_submitter(sub=f"lab-flag-intruder-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, owner)
    await _ensure_user(test_db, intruder)
    challenge = await _seed_challenge(test_db, slug=f"_lfo_{uuid.uuid4().hex[:6]}")

    async with _make_client(test_db, owner) as client:
        lab = (
            await client.post(f"/api/v1/challenges/{challenge.id}/lab/launch")
        ).json()
    app.dependency_overrides.clear()

    async with _make_client(test_db, intruder) as client:
        res = await client.post(
            f"/api/v1/challenges/{challenge.id}/submissions",
            json={"flag": CORRECT, "lab_id": lab["id"]},
        )
    assert res.status_code == 403
    app.dependency_overrides.clear()


async def test_lab_extension_preserves_python_fallback(test_db, monkeypatch):
    user = _student(sub=f"lab-extend-fallback-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, user)
    challenge = await _seed_challenge(test_db, slug=f"_lex_{uuid.uuid4().hex[:6]}")
    now = datetime.now(UTC)
    monkeypatch.setattr(
        lab_service, "get_settings",
        lambda: SimpleNamespace(rust_core_url="", lab_max_expiry_minutes=240),
    )
    async with test_db() as db:
        lab = LabInstance(
            user_id=user.id, challenge_id=challenge.id, status="running",
            expires_at=now + timedelta(minutes=30),
        )
        db.add(lab)
        await db.commit()
        result = await lab_service.extend_lab(db, user, lab, additional_minutes=30)
        assert result.status == "running"
        assert abs((result.expires_at.replace(tzinfo=UTC) - (
            now + timedelta(minutes=60)
        )).total_seconds()) < 3
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "lab.extend", AuditLog.target_id == str(lab.id),
        )) == 1


@pytest.mark.parametrize(
    ("reply", "http_status"),
    [
        ({"outcome": "not_found"}, 404),
        ({"outcome": "not_running", "current_status": "stopped"}, 400),
        ({"outcome": "not_running", "current_status": "untrusted"}, 503),
        ({"outcome": "expired"}, 400),
        ({"outcome": "untrusted"}, 503),
        ({"outcome": "extended", "current_status": "running"}, 503),
    ],
)
async def test_rust_lab_lease_outcomes_fail_closed(monkeypatch, reply, http_status):
    monkeypatch.setattr(rust_engine, "_post", AsyncMock(return_value=reply))
    with pytest.raises(HTTPException) as exc:
        await rust_engine.extend_lab_in_rust(
            str(uuid.uuid4()), str(uuid.uuid4()), ["student"], None, 30, 240,
        )
    assert exc.value.status_code == http_status
