import asyncio
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.db.session import get_db
from app.models.challenges import Challenge
from app.models.labs import LabInstance
from app.schemas.lab import LabAdminOut, LabExtendIn, LabListOut, LabOut
from app.services import labs as lab_service

router = APIRouter(tags=["labs"])


async def _get_published_challenge(db: AsyncSession, challenge_id: uuid.UUID) -> Challenge:
    challenge = await db.get(Challenge, challenge_id)
    if challenge is None or not challenge.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found"
        )
    return challenge


async def _get_lab(db: AsyncSession, lab_id: uuid.UUID) -> LabInstance:
    lab = await db.get(LabInstance, lab_id)
    if lab is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab not found")
    return lab


@router.post(
    "/challenges/{challenge_id}/lab/launch",
    response_model=LabOut,
    status_code=status.HTTP_201_CREATED,
)
async def launch_lab(
    challenge_id: uuid.UUID,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("lab.launch"))],
    sync: bool = True,
):
    """Provision an isolated lab for this challenge (per-user network)."""
    challenge = await _get_published_challenge(db, challenge_id)
    idempotency_key = request.headers.get("X-Idempotency-Key")
    out = await lab_service.launch_lab(
        db, user, challenge, sync=sync, idempotency_key=idempotency_key, request=request
    )
    if not sync:
        response.status_code = status.HTTP_202_ACCEPTED
    return out


@router.put("/labs/{lab_id}/extend", response_model=LabOut)
async def extend_lab(
    lab_id: uuid.UUID,
    payload: LabExtendIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("lab.launch"))],
):
    """Extend lease duration of a currently running lab."""
    lab = await _get_lab(db, lab_id)
    return await lab_service.extend_lab(
        db, user, lab, additional_minutes=payload.additional_minutes, request=request
    )


@router.get("/labs/{lab_id}/events")
async def lab_events(
    lab_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("lab.launch"))],
):
    """Server-Sent Events (SSE) stream for real-time lab provisioning and status."""
    lab = await _get_lab(db, lab_id)
    if not lab_service._can_manage_lab(user, lab):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    async def event_generator():
        for _ in range(60):
            if await request.is_disconnected():
                break
            await db.refresh(lab)
            current_status = lab.status
            payload = {
                "id": str(lab.id),
                "status": current_status,
                "connection_hint": lab.connection_hint,
                "error_message": lab.error_message,
                "expires_at": lab.expires_at.isoformat() if lab.expires_at else None,
            }
            yield f"data: {json.dumps(payload)}\n\n"
            if current_status in ("running", "failed", "stopped", "expired", "terminated"):
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/labs", response_model=list[LabOut])
async def my_labs(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("lab.launch"))],
):
    """My labs, newest first; expired running labs are auto-shut down."""
    return await lab_service.my_labs(db, user)


@router.post("/labs/{lab_id}/stop", response_model=LabOut)
async def stop_lab(
    lab_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("lab.launch"))],
):
    lab = await _get_lab(db, lab_id)
    return await lab_service.stop_lab(db, user, lab, request=request)


@router.post("/labs/{lab_id}/reset", response_model=LabOut)
async def reset_lab(
    lab_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("lab.launch"))],
):
    lab = await _get_lab(db, lab_id)
    return await lab_service.reset_lab(db, user, lab, request=request)


@router.post("/labs/{lab_id}/expire", response_model=LabOut)
async def expire_lab(
    lab_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("lab.launch"))],
):
    lab = await _get_lab(db, lab_id)
    return await lab_service.expire_lab(db, user, lab, request=request)


@router.get("/admin/labs", response_model=LabListOut)
async def admin_list_labs(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("lab.admin"))],
    status_filter: str | None = None,
    user_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """All labs across users (admin monitoring)."""
    items, total = await lab_service.admin_list_labs(
        db, status_filter=status_filter, user_id=user_id, limit=limit, offset=offset
    )
    return LabListOut(items=items, total=total, offset=offset, limit=limit)


@router.post("/admin/labs/{lab_id}/terminate", response_model=LabAdminOut)
async def admin_terminate_lab(
    lab_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("lab.admin"))],
):
    """Force-stop and expire another user's lab."""
    lab = await _get_lab(db, lab_id)
    return await lab_service.admin_terminate_lab(db, lab, user, request=request)


@router.get("/labs/{lab_id}/status")
async def lab_status(
    lab_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("lab.launch"))],
):
    """Real-time provider status for a lab (container/VM state)."""
    lab = await _get_lab(db, lab_id)
    return await lab_service.lab_provider_status(db, user, lab)


@router.get("/labs/{lab_id}/logs")
async def lab_logs(
    lab_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("lab.launch"))],
    tail: int = 100,
):
    """Recent log output from a lab environment."""
    lab = await _get_lab(db, lab_id)
    return await lab_service.lab_provider_logs(db, user, lab, tail=tail)