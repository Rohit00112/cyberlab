"""Lab lifecycle service (Phase 2 Cyber Range, PRD §46-§51).

Labs are provisioned server-side into a per-user isolated bridge network.
Students interact only through these endpoints — the Docker handle never
leaves the API service (PRD §54 "No direct student access to infrastructure").
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.infrastructure import docker as docker_adapter
from app.infrastructure.docker import DockerError
from app.models.challenges import Challenge
from app.models.labs import LabInstance
from app.schemas.lab import LabOut
from app.services.users import record_audit

ACTIVE_STATUSES = {"provisioning", "running"}
DOCKER_TIMEOUT = 30


async def _to_out(db: AsyncSession, lab: LabInstance) -> LabOut:
    await db.refresh(lab)
    challenge = await db.get(Challenge, lab.challenge_id)
    return LabOut(
        id=lab.id,
        challenge_id=lab.challenge_id,
        challenge_title=challenge.title if challenge else None,
        challenge_slug=challenge.slug if challenge else None,
        status=lab.status,
        connection_hint=lab.connection_hint,
        network_name=lab.network_name,
        container_name=lab.container_name,
        expires_at=lab.expires_at,
        created_at=lab.created_at,
        updated_at=lab.updated_at,
        error_message=lab.error_message,
    )


def _network_name(user_id: uuid.UUID) -> str:
    return f"cyberlab-{str(user_id)[:8]}"


async def launch_lab(
    db: AsyncSession,
    user: CurrentUser,
    challenge: Challenge,
    *,
    request: Request | None = None,
) -> LabOut:
    if not challenge.environment_type or challenge.environment_type == "none":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This challenge does not provide a lab environment.",
        )

    settings = get_settings()
    active = int(
        await db.scalar(
            select(func.count())
            .select_from(LabInstance)
            .where(
                LabInstance.user_id == user.id,
                LabInstance.status.in_(ACTIVE_STATUSES),
            )
        )
        or 0
    )
    if active >= settings.lab_max_instances_per_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Lab limit reached ({settings.lab_max_instances_per_user} active "
                "labs at a time). Stop or reset one first."
            ),
        )

    lab = LabInstance(
        user_id=user.id,
        challenge_id=challenge.id,
        status="provisioning",
        network_name=_network_name(user.id),
    )
    db.add(lab)
    await db.commit()
    await db.refresh(lab)

    try:
        await docker_adapter.ensure_network(lab.network_name)
        name = f"lab-{str(user.id)[:8]}-{str(lab.id)[:8]}"
        container_id, ip = await docker_adapter.create_and_start_container(
            name, settings.lab_image, lab.network_name
        )
        lab.container_id = container_id
        lab.container_name = name
        lab.connection_hint = (
            f"Container {name} is live at {ip} on isolated network {lab.network_name}. "
            f"Shares the {settings.lab_image} image; will expire in "
            f"{settings.lab_default_expiry_minutes} minutes."
        )
        lab.status = "running"
        lab.expires_at = datetime.now(UTC) + timedelta(
            minutes=settings.lab_default_expiry_minutes
        )
    except DockerError as exc:
        lab.status = "error"
        lab.error_message = str(exc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Lab provisioning failed — infrastructure unavailable: {exc}",
        ) from None
    except Exception as exc:
        lab.status = "error"
        lab.error_message = str(exc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Lab provisioning failed — unexpected error: {exc}",
        ) from exc

    await db.commit()
    await db.refresh(lab)
    await record_audit(
        db, event="lab.launch", user_id=user.id, target_id=challenge.slug, request=request
    )
    return await _to_out(db, lab)


def _can_manage_lab(user: CurrentUser, lab: LabInstance) -> bool:
    from app.core.permissions import has_permission

    return lab.user_id == user.id or has_permission(user.roles, "lab.admin")


async def stop_lab(
    db: AsyncSession,
    user: CurrentUser,
    lab: LabInstance,
    *,
    request: Request | None = None,
) -> LabOut:
    if not _can_manage_lab(user, lab):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if lab.status == "running" and lab.container_id:
        try:
            await docker_adapter.stop_container(lab.container_id)
        except DockerError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from None
    lab.status = "stopped"
    await db.commit()
    await record_audit(
        db, event="lab.stop", user_id=user.id, target_id=str(lab.id), request=request
    )
    return await _to_out(db, lab)


async def reset_lab(
    db: AsyncSession,
    user: CurrentUser,
    lab: LabInstance,
    *,
    request: Request | None = None,
) -> LabOut:
    if not _can_manage_lab(user, lab):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    settings = get_settings()
    if lab.container_id:
        try:
            await docker_adapter.remove_container(lab.container_id)
        except DockerError:
            pass

    name = f"lab-{str(user.id)[:8]}-{str(lab.id)[:8]}"
    try:
        await docker_adapter.ensure_network(lab.network_name)
        container_id, ip = await docker_adapter.create_and_start_container(
            name, settings.lab_image, lab.network_name
        )
        lab.container_id = container_id
        lab.container_name = name
        lab.connection_hint = (
            f"Container {name} is live at {ip} on isolated network {lab.network_name}."
        )
        lab.status = "running"
        lab.expires_at = datetime.now(UTC) + timedelta(
            minutes=settings.lab_default_expiry_minutes
        )
        lab.error_message = None
    except DockerError as exc:
        lab.status = "error"
        lab.error_message = str(exc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Lab reset failed — infrastructure unavailable: {exc}",
        ) from None
    except Exception as exc:
        lab.status = "error"
        lab.error_message = str(exc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Lab reset failed — unexpected error: {exc}",
        ) from exc

    await db.commit()
    await db.refresh(lab)
    await record_audit(
        db, event="lab.reset", user_id=user.id, target_id=str(lab.id), request=request
    )
    return await _to_out(db, lab)


async def expire_lab(
    db: AsyncSession,
    user: CurrentUser,
    lab: LabInstance,
    *,
    request: Request | None = None,
) -> LabOut:
    if not _can_manage_lab(user, lab):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if lab.status == "running" and lab.container_id:
        try:
            await docker_adapter.stop_container(lab.container_id)
        except DockerError:
            pass
    lab.status = "expired"
    await db.commit()
    await record_audit(
        db, event="lab.expire", user_id=user.id, target_id=str(lab.id), request=request
    )
    return await _to_out(db, lab)


async def my_labs(db: AsyncSession, user: CurrentUser) -> list[LabOut]:
    rows = (
        await db.scalars(
            select(LabInstance)
            .where(LabInstance.user_id == user.id)
            .order_by(LabInstance.created_at.desc())
        )
    ).all()

    shadowed: bool = False
    now = datetime.now(UTC)
    settings = get_settings()
    for lab in rows:
        if (
            lab.status == "running"
            and lab.expires_at
            and now > lab.expires_at.replace(tzinfo=UTC)
        ):
            if lab.container_id:
                try:
                    await docker_adapter.stop_container(lab.container_id)
                except DockerError:
                    pass
            lab.status = "expired"
            shadowed = True
        elif lab.status == "provisioning" and lab.created_at:
            if now - lab.created_at.replace(tzinfo=UTC) > timedelta(
                minutes=settings.lab_provisioning_timeout_minutes
            ):
                lab.status = "error"
                lab.error_message = "Provisioning timed out."
                shadowed = True
    if shadowed:
        await db.commit()

    return [await _to_out(db, lab) for lab in rows]