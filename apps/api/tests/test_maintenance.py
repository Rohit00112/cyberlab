"""Tests for the background maintenance sweep (expiry / provisioning timeout)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.infrastructure.docker import DockerError
from app.models import AuditLog, Challenge, LabInstance, ProvisioningJob, User
from app.services.labs import expire_stale_labs


async def _seed_user_and_challenge(test_db) -> tuple[uuid.UUID, uuid.UUID]:
    async with test_db() as db:
        user = User(
            keycloak_sub=f"sweep-{uuid.uuid4().hex[:6]}",
            email=f"sweep-{uuid.uuid4().hex[:6]}@cyberlab.test",
            display_name="Sweep Test",
        )
        db.add(user)
        await db.flush()
        challenge = Challenge(
            slug=f"_sweep_{uuid.uuid4().hex[:6]}",
            title="Sweep challenge",
            description="desc",
            category="Linux",
            difficulty="beginner",
            points=100,
            status="published",
            environment_type="docker",
        )
        db.add(challenge)
        await db.commit()
        return user.id, challenge.id


async def _add_lab(test_db, user_id: uuid.UUID, challenge_id: uuid.UUID, **kwargs):
    async with test_db() as db:
        lab = LabInstance(user_id=user_id, challenge_id=challenge_id, **kwargs)
        db.add(lab)
        await db.commit()
        return lab


async def test_sweep_expires_overdue_running_lab(test_db, monkeypatch):
    user_id, challenge_id = await _seed_user_and_challenge(test_db)
    await _add_lab(
        test_db,
        user_id,
        challenge_id,
        status="running",
        container_id="host-1",
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    called = {"stopped": []}

    async def stop_container(container_id: str) -> None:
        called["stopped"].append(container_id)

    monkeypatch.setattr("app.services.labs.docker_adapter.stop_container", stop_container)

    async with test_db() as db:
        changed = await expire_stale_labs(db)

    assert changed == 1
    assert called["stopped"] == ["host-1"]
    async with test_db() as db:
        lab = (await db.scalars(select(LabInstance))).one()
        assert lab.status == "expired"
        assert (await db.scalars(select(AuditLog.event))).all() == ["lab.expire_auto"]


async def test_sweep_flags_provisioning_stuck_lab(test_db, monkeypatch):
    user_id, challenge_id = await _seed_user_and_challenge(test_db)
    await _add_lab(
        test_db,
        user_id,
        challenge_id,
        status="provisioning",
        created_at=datetime.now(UTC) - timedelta(minutes=30),
    )

    async with test_db() as db:
        changed = await expire_stale_labs(db)

    assert changed == 1
    async with test_db() as db:
        lab = (await db.scalars(select(LabInstance))).one()
        assert lab.status == "error"
        assert lab.error_message == "Provisioning timed out."
        assert (await db.scalars(select(AuditLog.event))).all() == [
            "lab.provisioning_timeout",
        ]


async def test_provisioning_timeout_uses_claim_time_and_fails_job_atomically(test_db):
    user_id, challenge_id = await _seed_user_and_challenge(test_db)
    lab = await _add_lab(
        test_db, user_id, challenge_id,
        status="provisioning", created_at=datetime.now(UTC) - timedelta(hours=3),
    )
    async with test_db() as db:
        job = ProvisioningJob(
            lab_instance_id=lab.id, user_id=user_id, challenge_id=challenge_id,
            status="running", started_at=datetime.now(UTC),
        )
        db.add(job)
        await db.commit()
        job_id = job.id

    async with test_db() as db:
        assert await expire_stale_labs(db) == 0
    async with test_db() as db:
        assert (await db.get(LabInstance, lab.id)).status == "provisioning"
        job = await db.get(ProvisioningJob, job_id)
        job.started_at = datetime.now(UTC) - timedelta(minutes=40)
        await db.commit()

    async with test_db() as db:
        assert await expire_stale_labs(db) == 1
    async with test_db() as db:
        assert (await db.get(LabInstance, lab.id)).status == "error"
        job = await db.get(ProvisioningJob, job_id)
        assert job.status == "failed"
        assert job.completed_at is not None
        event = (await db.scalars(select(AuditLog))).one()
        assert event.event == "lab.provisioning_timeout"
        assert event.details == {"job_id": str(job_id)}


async def test_sweep_does_not_hide_unstopped_running_lab(test_db, monkeypatch):
    user_id, challenge_id = await _seed_user_and_challenge(test_db)
    lab = await _add_lab(
        test_db, user_id, challenge_id,
        status="running", container_id="unreachable-provider",
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )

    async def stop_fails(_ref: str) -> None:
        raise DockerError("cannot stop the environment")

    monkeypatch.setattr("app.services.labs.docker_adapter.stop_container", stop_fails)
    async with test_db() as db:
        assert await expire_stale_labs(db) == 0
    async with test_db() as db:
        assert (await db.get(LabInstance, lab.id)).status == "running"
        assert (await db.scalars(select(AuditLog.event))).all() == []


async def test_sweep_cannot_expire_running_lab_without_provider_handle(test_db):
    user_id, challenge_id = await _seed_user_and_challenge(test_db)
    lab = await _add_lab(
        test_db, user_id, challenge_id,
        status="running", expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    async with test_db() as db:
        assert await expire_stale_labs(db) == 0
    async with test_db() as db:
        assert (await db.get(LabInstance, lab.id)).status == "running"
        assert (await db.scalars(select(AuditLog.event))).all() == []


async def test_sweep_leaves_active_lab_untouched(test_db, monkeypatch):
    user_id, challenge_id = await _seed_user_and_challenge(test_db)
    await _add_lab(
        test_db,
        user_id,
        challenge_id,
        status="running",
        container_id="host-2",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )

    stopped = []

    async def stop_container(container_id: str) -> None:
        stopped.append(container_id)

    monkeypatch.setattr("app.services.labs.docker_adapter.stop_container", stop_container)

    async with test_db() as db:
        changed = await expire_stale_labs(db)

    assert changed == 0
    assert stopped == []
