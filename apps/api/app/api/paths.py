"""API router for learning paths."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user_or_none, require_permission
from app.db.session import get_db
from app.schemas.learning_path import (
    LearningPathCreate,
    LearningPathDetail,
    LearningPathStepCreate,
    LearningPathSummary,
)
from app.services import learning_paths as path_service

router = APIRouter(tags=["learning paths"])

@router.get("/paths", response_model=list[LearningPathSummary])
async def list_paths(
    db: Annotated[AsyncSession, Depends(get_db)]
):
    return await path_service.list_published_paths(db)


@router.get("/admin/paths", response_model=list[LearningPathSummary])
async def admin_list_paths(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("learning_path.manage"))],
):
    return await path_service.list_all_paths(db)

@router.get("/paths/{path_id}", response_model=LearningPathDetail)
async def get_path(
    path_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(current_user_or_none)]
):
    return await path_service.get_path_with_progress(db, path_id, user.id if user else None)

@router.post("/paths", response_model=LearningPathSummary, status_code=status.HTTP_201_CREATED)
async def create_path(
    data: LearningPathCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("learning_path.manage"))]
):
    return await path_service.create_learning_path(db, data)

@router.post("/paths/{path_id}/steps", status_code=status.HTTP_201_CREATED)
async def add_path_step(
    path_id: uuid.UUID,
    data: LearningPathStepCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("learning_path.manage"))]
):
    await path_service.add_step(db, path_id, data.challenge_id, data.step_order)
    return {"message": "Step added"}
