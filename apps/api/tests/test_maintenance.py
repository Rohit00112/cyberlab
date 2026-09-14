"""Tests for the background maintenance sweep (expiry / provisioning timeout)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import Challenge, LabInstance, User
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