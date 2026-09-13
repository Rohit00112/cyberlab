"""Skill, profile and analytics endpoints (Phase 4, PRD §25-28)."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.db.session import get_db
from app.schemas.skill import (
    ChallengeDifficultyOut,
    SkillAggregate,
    SkillCreate,
    SkillOut,
    SkillProfileOut,
    SkillUpdate,
    StudentAnalyticsOut,
)
from app.services import skills as skill_service

router = APIRouter(tags=["skills"])


@router.get("/skills", response_model=list[SkillOut])
async def list_skills(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Public skill taxonomy."""
    return await skill_service.list_skills(db)


@router.get("/skills/me", response_model=SkillProfileOut)
async def my_skill_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("skill.view"))],
):
    return await skill_service.get_skill_profile(db, user.id)


@router.get("/admin/skills", response_model=list[SkillOut])
async def admin_list_skills(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("skill.manage"))],
):
    return await skill_service.list_skills(db, include_inactive=True, with_counts=True)


@router.post("/admin/skills", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
async def create_skill(
    data: SkillCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("skill.manage"))],
):
    return await skill_service.create_skill(db, data, user.id, request=request)


@router.patch("/admin/skills/{skill_id}", response_model=SkillOut)
async def update_skill(
    skill_id: uuid.UUID,
    data: SkillUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("skill.manage"))],
):
    skill = await skill_service.get_skill(db, skill_id)
    return await skill_service.update_skill(db, skill, data, user.id, request=request)


@router.get("/analytics/skills", response_model=list[SkillAggregate])
async def analytics_skills(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("analytics.view"))],
):
    """Per-skill competency aggregate across students (PRD §27)."""
    return await skill_service.skill_analytics(db)


@router.get("/analytics/students/{user_id}", response_model=StudentAnalyticsOut)
async def analytics_student(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("analytics.view"))],
):
    """Student-level analytics: history, skill evidence, hints, badges (PRD §27)."""
    return await skill_service.student_analytics(db, user_id)


@router.get(
    "/analytics/challenges/{challenge_id}/difficulty", response_model=ChallengeDifficultyOut
)
async def analytics_challenge_difficulty(
    challenge_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("analytics.view"))],
):
    """Advisory difficulty indicators for one challenge (PRD §28)."""
    return await skill_service.challenge_difficulty_stats(db, challenge_id)