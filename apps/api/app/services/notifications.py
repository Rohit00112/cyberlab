"""Notification and announcement service (Track 3).

Handles CRUD for notifications, broadcast logic, and SSE connection tracking
for real-time push.
"""
from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notifications import Announcement, Notification
from app.schemas.notification import AnnouncementOut, NotificationOut

# In-memory SSE connection registry: user_id -> set[asyncio.Queue]
_sse_connections: dict[uuid.UUID, set[asyncio.Queue]] = defaultdict(set)


def subscribe(user_id: uuid.UUID) -> asyncio.Queue:
    """Register an SSE listener for a user. Returns a queue that receives events."""
    queue: asyncio.Queue = asyncio.Queue()
    _sse_connections[user_id].add(queue)
    return queue


def unsubscribe(user_id: uuid.UUID, queue: asyncio.Queue) -> None:
    """Remove an SSE listener."""
    _sse_connections[user_id].discard(queue)
    if not _sse_connections[user_id]:
        del _sse_connections[user_id]


async def _push_to_user(user_id: uuid.UUID, notification: NotificationOut) -> None:
    """Push a notification to all SSE connections for a user."""
    for queue in list(_sse_connections.get(user_id, set())):
        try:
            queue.put_nowait(notification)
        except asyncio.QueueFull:
            pass


async def create_notification(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    title: str,
    body: str,
    link: str | None = None,
    source: str = "system",
) -> NotificationOut:
    """Create a notification for a specific user and push via SSE."""
    notification = Notification(
        user_id=user_id,
        title=title,
        body=body,
        link=link,
        source=source,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    out = NotificationOut.model_validate(notification)
    await _push_to_user(user_id, out)
    return out


async def broadcast_notification(
    db: AsyncSession,
    *,
    title: str,
    body: str,
    link: str | None = None,
    source: str = "announcement",
) -> NotificationOut:
    """Create a broadcast notification (user_id=NULL) visible to all."""
    notification = Notification(
        user_id=None,
        title=title,
        body=body,
        link=link,
        source=source,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    out = NotificationOut.model_validate(notification)
    # Push to all connected users
    for user_id in list(_sse_connections.keys()):
        await _push_to_user(user_id, out)
    return out


async def list_notifications(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    limit: int = 50,
) -> tuple[list[NotificationOut], int]:
    """List notifications for a user (their own + broadcasts), newest first."""
    conditions = or_(
        Notification.user_id == user_id,
        Notification.user_id.is_(None),
    )
    total_unread = int(
        await db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(conditions, Notification.is_read.is_(False))
        )
        or 0
    )
    rows = (
        await db.scalars(
            select(Notification)
            .where(conditions)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [NotificationOut.model_validate(n) for n in rows], total_unread


async def mark_read(
    db: AsyncSession,
    notification_id: uuid.UUID,
    user_id: uuid.UUID,
) -> NotificationOut | None:
    """Mark a notification as read."""
    notification = await db.get(Notification, notification_id)
    if notification is None:
        return None
    # Only the target user (or broadcast recipient) can mark as read
    if notification.user_id is not None and notification.user_id != user_id:
        return None
    notification.is_read = True
    await db.commit()
    await db.refresh(notification)
    return NotificationOut.model_validate(notification)


async def create_announcement(
    db: AsyncSession,
    *,
    title: str,
    body: str,
    author_id: uuid.UUID,
    target: str = "all",
) -> AnnouncementOut:
    """Create an announcement and broadcast a notification."""
    announcement = Announcement(
        title=title,
        body=body,
        author_id=author_id,
        target=target,
    )
    db.add(announcement)
    await db.commit()
    await db.refresh(announcement)

    # Broadcast notification
    await broadcast_notification(
        db,
        title=title,
        body=body,
        link="/announcements",
        source="announcement",
    )

    return AnnouncementOut.model_validate(announcement)


async def list_announcements(
    db: AsyncSession,
    *,
    limit: int = 50,
) -> list[AnnouncementOut]:
    """List all announcements, newest first."""
    rows = (
        await db.scalars(
            select(Announcement)
            .order_by(Announcement.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [AnnouncementOut.model_validate(a) for a in rows]
