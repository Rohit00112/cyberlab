"""API router for the research platform (Phase 6, PRD §70-§72).

All endpoints require the ``analytics.research`` permission (researcher role).
Dataset/experiment deletion additionally requires ownership or ``user.manage``.
Exports are pseudonymized by construction (see ``services/research.py``).
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.core.permissions import has_permission
from app.db.session import get_db
from app.schemas.research import (
    DatasetCreate,
    ExperimentCreate,
    ExperimentUpdate,
    ResearchDatasetOut,
    ResearchExperimentOut,
    ResearchGraphOut,
    ResearchMetricsOut,
)
from app.services import research as research_service
from app.services.users import record_audit

router = APIRouter(tags=["research"])

researcher = Annotated[CurrentUser, Depends(require_permission("analytics.research"))]


def _ensure_owner(user: CurrentUser, owner_id: uuid.UUID | None) -> None:
    if owner_id != user.id and not has_permission(user.roles, "user.manage"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


@router.post(
    "/research/datasets", response_model=ResearchDatasetOut, status_code=status.HTTP_201_CREATED
)
async def create_research_dataset(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: researcher,
    data: DatasetCreate,
):
    return await research_service.build_dataset(db, data, created_by=user.id)


@router.get("/research/datasets", response_model=list[ResearchDatasetOut])
async def list_research_datasets(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: researcher,
):
    return await research_service.list_datasets(db)


@router.get("/research/datasets/{dataset_id}", response_model=ResearchDatasetOut)
async def get_research_dataset(
    dataset_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: researcher,
):
    return ResearchDatasetOut.model_validate(
        await research_service.get_dataset(db, dataset_id)
    )


@router.get("/research/datasets/{dataset_id}/download")
async def download_research_dataset(
    dataset_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: researcher,
    request: Request,
    format: str = "csv",
):
    dataset = await research_service.get_dataset(db, dataset_id)
    await research_service.ensure_active(dataset)
    path = research_service.dataset_artifact_path(dataset)
    if format == "json":
        path = path.with_suffix(".json")
    elif format != "csv":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="format must be csv or json"
        )
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact missing")
    media_type = "application/json" if format == "json" else "text/csv"
    await record_audit(
        db,
        event="research.dataset.download",
        user_id=user.id,
        target_id=str(dataset.id),
        details={"format": format, "kind": dataset.kind, "rows": dataset.row_count},
        request=request,
    )
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.delete("/research/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_research_dataset(
    dataset_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: researcher,
):
    dataset = await research_service.get_dataset(db, dataset_id)
    _ensure_owner(user, dataset.created_by)
    await research_service.delete_dataset(db, dataset)


@router.get("/research/metrics", response_model=ResearchMetricsOut)
async def research_metrics(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: researcher,
):
    return await research_service.research_metrics(db)


@router.get("/research/graph", response_model=ResearchGraphOut)
async def research_graph(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: researcher,
):
    return await research_service.research_graph(db)


@router.post(
    "/research/experiments",
    response_model=ResearchExperimentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_experiment(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: researcher,
    data: ExperimentCreate,
):
    return await research_service.create_experiment(
        db,
        name=data.name,
        model_ref=data.model_ref,
        description=data.description,
        params=data.params,
        created_by=user.id,
    )


@router.get("/research/experiments", response_model=list[ResearchExperimentOut])
async def list_experiments(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: researcher,
):
    return await research_service.list_experiments(db)


@router.get("/research/experiments/{experiment_id}", response_model=ResearchExperimentOut)
async def get_experiment(
    experiment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: researcher,
):
    return ResearchExperimentOut.model_validate(
        await research_service.get_experiment(db, experiment_id)
    )


@router.patch("/research/experiments/{experiment_id}", response_model=ResearchExperimentOut)
async def update_experiment(
    experiment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: researcher,
    data: ExperimentUpdate,
):
    experiment = await research_service.get_experiment(db, experiment_id)
    _ensure_owner(user, experiment.created_by)
    return await research_service.update_experiment(
        db, experiment, status_value=data.status, metrics=data.metrics
    )


@router.delete("/research/experiments/{experiment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_experiment(
    experiment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: researcher,
):
    experiment = await research_service.get_experiment(db, experiment_id)
    _ensure_owner(user, experiment.created_by)
    await research_service.delete_experiment(db, experiment)