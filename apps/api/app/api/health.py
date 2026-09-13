"""Health and readiness endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.infrastructure import docker as docker_adapter
from app.models.labs import LabInstance

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "cyberlab-api"}


@router.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)) -> dict[str, str]:  # noqa: B008
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@router.get("/health/lab")
async def health_lab(db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    """Docker reachability plus live lab counts (admin console)."""
    try:
        docker_ok = await docker_adapter.docker_ping()
    except Exception:
        docker_ok = False
    running = int(
        await db.scalar(
            select(func.count()).select_from(LabInstance).where(LabInstance.status == "running")
        )
        or 0
    )
    provisioning = int(
        await db.scalar(
            select(func.count())
            .select_from(LabInstance)
            .where(LabInstance.status == "provisioning")
        )
        or 0
    )
    total = int(
        await db.scalar(select(func.count()).select_from(LabInstance)) or 0
    )
    return {
        "status": "ok" if docker_ok else "degraded",
        "docker": {"reachable": docker_ok},
        "labs": {
            "running": running,
            "provisioning": provisioning,
            "total": total,
        },
    }