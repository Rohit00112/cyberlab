"""Lab endpoints (Phase 2 Cyber Range, PRD §46-§51)."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.db.session import get_db
from app.models.challenges import Challenge
from app.models.labs import LabInstance
from app.schemas.lab import LabAdminOut, LabListOut, LabOut
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
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("lab.launch"))],
):
    """Provision an isolated lab for this challenge (per-user network)."""
    challenge = await _get_published_challenge(db, challenge_id)
    return await lab_service.launch_lab(db, user, challenge, request=request)


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