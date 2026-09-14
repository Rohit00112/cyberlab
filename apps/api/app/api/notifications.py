"""Notification and announcement API routes (Track 3).

Endpoints:
  - GET  /notifications          — user's notifications
  - POST /notifications/{id}/read — mark as read
  - GET  /notifications/stream   — SSE stream for real-time push
  - POST /announcements          — create announcement (faculty/admin)
  - GET  /announcements          — list announcements
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.db.session import get_db
from app.schemas.notification import (
    AnnouncementCreate,
    AnnouncementOut,
    NotificationListOut,
    NotificationOut,
)
from app.services import notifications as notif_service

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=NotificationListOut)
async def list_notifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
    limit: int = 50,
):
    """List current user's notifications (own + broadcasts)."""
    items, unread_count = await notif_service.list_notifications(db, user.id, limit=limit)
    return NotificationListOut(items=items, unread_count=unread_count)


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_read(
    notification_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
):
    """Mark a notification as read."""
    result = await notif_service.mark_read(db, notification_id, user.id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found"
        )
    return result


@router.get("/notifications/stream")
async def notification_stream(
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
):
    """SSE stream for real-time notification push."""
    queue = notif_service.subscribe(user.id)

    async def event_generator():
        try:
            # Send an initial keepalive
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    notification = await asyncio.wait_for(queue.get(), timeout=30)
                    data = notification.model_dump_json()
                    yield f"event: notification\ndata: {data}\n\n"
                except TimeoutError:
                    # Send keepalive ping
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            notif_service.unsubscribe(user.id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/announcements",
    response_model=AnnouncementOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_announcement(
    data: AnnouncementCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("competition.manage"))],
):
    """Create a new announcement (faculty/admin)."""
    return await notif_service.create_announcement(
        db,
        title=data.title,
        body=data.body,
        author_id=user.id,
        target=data.target,
    )


@router.get("/announcements", response_model=list[AnnouncementOut])
async def list_announcements(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
    limit: int = 50,
):
    """List all announcements."""
    return await notif_service.list_announcements(db, limit=limit)
