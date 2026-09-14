"""Tests for notification and announcement service and endpoints (Track 3)."""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest

from app.models.users import User
from app.schemas.notification import NotificationOut
from app.services import notifications as notif_service


async def _make_user(db, user_id: uuid.UUID | None = None) -> User:
    uid = user_id or uuid.uuid4()
    u = User(
        id=uid,
        keycloak_sub=f"sub-{uid.hex[:8]}",
        email=f"user-{uid.hex[:8]}@cyberlab.test",
        display_name=f"User {uid.hex[:4]}",
    )
    db.add(u)
    await db.flush()
    return u


@pytest.mark.asyncio
async def test_create_and_list_notifications(test_db):
    async with test_db() as db:
        u1 = await _make_user(db)
        u2 = await _make_user(db)
        user_id = u1.id
        other_user_id = u2.id

        # Create user-specific notification
        n1 = await notif_service.create_notification(
            db,
            user_id=user_id,
            title="Lab Ready",
            body="Your lab is ready to access.",
            link="/labs/123",
            source="lab",
        )
        assert n1.title == "Lab Ready"
        assert n1.is_read is False
        assert n1.source == "lab"

        # Create another notification for other user
        await notif_service.create_notification(
            db,
            user_id=other_user_id,
            title="Private",
            body="Not for user_id",
        )

        # Create broadcast notification
        b1 = await notif_service.broadcast_notification(
            db,
            title="Platform Maintenance",
            body="Maintenance tonight at midnight.",
            link="/maintenance",
        )
        assert b1.user_id is None

        # List notifications for user_id: should see n1 and b1, not other_user's
        items, unread = await notif_service.list_notifications(db, user_id)
        assert unread == 2
        titles = [i.title for i in items]
        assert "Lab Ready" in titles
        assert "Platform Maintenance" in titles
        assert "Private" not in titles


@pytest.mark.asyncio
async def test_mark_notification_read(test_db):
    async with test_db() as db:
        u1 = await _make_user(db)
        u2 = await _make_user(db)
        user_id = u1.id
        other_user = u2.id

        n = await notif_service.create_notification(
            db,
            user_id=user_id,
            title="Unread Alert",
            body="Important update",
        )
        assert n.is_read is False

        # Attempt to mark read by another user should return None
        res_fail = await notif_service.mark_read(db, n.id, other_user)
        assert res_fail is None

        # Mark read by owner
        res_ok = await notif_service.mark_read(db, n.id, user_id)
        assert res_ok is not None
        assert res_ok.is_read is True

        # Non-existent notification
        res_none = await notif_service.mark_read(db, uuid.uuid4(), user_id)
        assert res_none is None


@pytest.mark.asyncio
async def test_announcements_and_broadcast(test_db):
    async with test_db() as db:
        author = await _make_user(db)
        viewer = await _make_user(db)

        ann = await notif_service.create_announcement(
            db,
            title="Competition Starting Soon",
            body="The Fall CTF begins in 1 hour.",
            author_id=author.id,
            target="competition:fall-ctf",
        )
        assert ann.title == "Competition Starting Soon"
        assert ann.target == "competition:fall-ctf"

        # Should list announcements
        all_ann = await notif_service.list_announcements(db)
        assert any(a.id == ann.id for a in all_ann)

        # Should have created a broadcast notification
        items, _ = await notif_service.list_notifications(db, viewer.id)
        assert any(i.title == "Competition Starting Soon" for i in items)


@pytest.mark.asyncio
async def test_sse_subscribe_and_push():
    user_id = uuid.uuid4()
    queue = notif_service.subscribe(user_id)
    try:
        dummy = NotificationOut(
            id=uuid.uuid4(),
            user_id=user_id,
            title="Realtime",
            body="Stream event",
            link=None,
            is_read=False,
            source="test",
            created_at=datetime.now(UTC),
        )
        await notif_service._push_to_user(user_id, dummy)
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event.title == "Realtime"
    finally:
        notif_service.unsubscribe(user_id, queue)


@pytest.mark.asyncio
async def test_notification_endpoints(student_client, test_db):
    client, user = student_client

    async with test_db() as db:
        n = await notif_service.create_notification(
            db,
            user_id=user.id,
            title="Test Notice",
            body="Notice body",
        )

    # GET /notifications
    res = await client.get("/api/v1/notifications")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "unread_count" in data
    assert any(i["id"] == str(n.id) for i in data["items"])

    # POST /notifications/{id}/read
    res_read = await client.post(f"/api/v1/notifications/{n.id}/read")
    assert res_read.status_code == 200
    assert res_read.json()["is_read"] is True

    # GET /announcements
    res_ann = await client.get("/api/v1/announcements")
    assert res_ann.status_code == 200
    assert isinstance(res_ann.json(), list)
