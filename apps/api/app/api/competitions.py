"""Competition endpoints (Phase 3, PRD §24)."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user_or_none, require_permission
from app.db.session import get_db
from app.models.competitions import Competition
from app.schemas.competition import (
    CompetitionChallengeAdd,
    CompetitionCreate,
    CompetitionLeaderboardOut,
    CompetitionOut,
    CompetitionSummary,
    CompetitionTransitionIn,
    CompetitionUpdate,
    TeamCreateIn,
)
from app.services import competitions as competition_service

router = APIRouter(tags=["competitions"])


async def _get_competition(db: AsyncSession, competition_id: uuid.UUID) -> Competition:
    competition = await db.get(Competition, competition_id)
    if competition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competition not found")
    return competition


@router.get("/competitions", response_model=list[CompetitionSummary])
async def list_competitions(
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = None,
):
    """All competitions (public catalogue)."""
    return await competition_service.list_competitions(db, filter_status=status_filter)


@router.post(
    "/competitions",
    response_model=CompetitionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_competition(
    data: CompetitionCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("competition.create"))],
):
    return await competition_service.create_competition(db, data, user, request=request)


@router.get("/competitions/{competition_id}", response_model=CompetitionOut)
async def get_competition(
    competition_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(current_user_or_none)],
):
    """Detail, including the subset of challenges each viewer may see.

    Rules and the enrolled status are included for the requesting user.
    """
    competition = await _get_competition(db, competition_id)
    return await competition_service.get_competition(
        db,
        competition,
        user=user,
        include_rules=competition.status
        in ("scheduled", "live", "finished", "archived"),
    )


@router.patch("/competitions/{competition_id}", response_model=CompetitionOut)
async def update_competition(
    competition_id: uuid.UUID,
    data: CompetitionUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("competition.manage"))],
):
    competition = await _get_competition(db, competition_id)
    return await competition_service.update_competition(
        db, competition, data, user, request=request
    )


@router.post("/competitions/{competition_id}/transition", response_model=CompetitionOut)
async def transition_competition(
    competition_id: uuid.UUID,
    data: CompetitionTransitionIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("competition.manage"))],
):
    competition = await _get_competition(db, competition_id)
    return await competition_service.transition(db, competition, data.action, user, request=request)


@router.post("/competitions/{competition_id}/challenges", response_model=CompetitionOut)
async def add_challenge(
    competition_id: uuid.UUID,
    data: CompetitionChallengeAdd,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("competition.manage"))],
):
    competition = await _get_competition(db, competition_id)
    return await competition_service.add_challenge(
        db, competition, data.challenge_id, data.points, user, request=request
    )


@router.delete(
    "/competitions/{competition_id}/challenges/{challenge_id}", response_model=CompetitionOut
)
async def remove_challenge(
    competition_id: uuid.UUID,
    challenge_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("competition.manage"))],
):
    competition = await _get_competition(db, competition_id)
    return await competition_service.remove_challenge(
        db, competition, challenge_id, user, request=request
    )


@router.post("/competitions/{competition_id}/register", response_model=CompetitionOut)
async def register(
    competition_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.attempt"))],
):
    competition = await _get_competition(db, competition_id)
    return await competition_service.register(db, competition, user, request=request)


@router.post("/competitions/{competition_id}/unregister", response_model=CompetitionOut)
async def unregister(
    competition_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.attempt"))],
):
    competition = await _get_competition(db, competition_id)
    return await competition_service.unregister(db, competition, user, request=request)


@router.post("/competitions/{competition_id}/teams", response_model=CompetitionOut)
async def create_team(
    competition_id: uuid.UUID,
    data: TeamCreateIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.attempt"))],
):
    competition = await _get_competition(db, competition_id)
    return await competition_service.create_team(db, competition, data.name, user, request=request)


@router.post("/competitions/{competition_id}/teams/{team_id}/join", response_model=CompetitionOut)
async def join_team(
    competition_id: uuid.UUID,
    team_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.attempt"))],
):
    competition = await _get_competition(db, competition_id)
    return await competition_service.join_team(db, competition, team_id, user, request=request)


@router.get("/competitions/{competition_id}/leaderboard", response_model=CompetitionLeaderboardOut)
async def competition_leaderboard(
    competition_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser | None, Depends(current_user_or_none)],
):
    competition = await _get_competition(db, competition_id)
    return CompetitionLeaderboardOut(
        items=await competition_service.leaderboard(db, competition)
    )


@router.post("/competitions/{competition_id}/freeze", response_model=CompetitionOut)
async def freeze_leaderboard(
    competition_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("competition.manage"))],
):
    competition = await _get_competition(db, competition_id)
    return await competition_service.freeze(db, competition, user, frozen=True, request=request)


@router.post("/competitions/{competition_id}/unfreeze", response_model=CompetitionOut)
async def unfreeze_leaderboard(
    competition_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("competition.manage"))],
):
    competition = await _get_competition(db, competition_id)
    return await competition_service.freeze(db, competition, user, frozen=False, request=request)