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
from app.core.flags import generate_lab_flag, hash_flag
from app.infrastructure import docker as docker_adapter
from app.infrastructure.docker import DockerError
from app.models.challenges import Challenge
from app.models.labs import LabInstance
from app.models.users import User
from app.schemas.lab import LabAdminOut, LabOut
from app.services.users import record_audit

ACTIVE_STATUSES = {"provisioning", "running"}
DOCKER_TIMEOUT = 30


def _lab_settings(challenge: Challenge | None) -> dict:
    """Resolve effective lab config from the challenge, with server-enforced caps."""
    settings = get_settings()
    cfg = (challenge.lab_config or {}) if challenge else {}
    image = cfg.get("image") or settings.lab_image
    expiry = cfg.get("expiry_minutes") or settings.lab_default_expiry_minutes
    max_instances = cfg.get("max_instances")
    flag_path = cfg.get("flag_path") or "/flag.txt"
    caps = {
        "image": image,
        "expiry_minutes": max(
            settings.lab_default_expiry_minutes, min(int(expiry), settings.lab_max_expiry_minutes)
        ),
        "max_instances": (
            int(max_instances) if isinstance(max_instances, int) and max_instances >= 1 else None
        ),
        "flag_path": flag_path,
    }
    return caps


def _container_name(lab: LabInstance) -> str:
    return f"lab-{str(lab.user_id)[:8]}-{str(lab.id)[:8]}"


def _flag_command(flag_path: str, flag: str) -> list[str]:
    """Shell command that writes the per-session flag into the container then parks it."""
    return ["/bin/sh", "-c", f"printf '%s\\n' '{flag}' > {flag_path} && sleep infinity"]


async def _start_container(lab: LabInstance, lab_cfg: dict) -> None:
    """Create and start the container, injecting a fresh per-session flag.

    Fills ``container_id``/``container_name``/``flag_hash``/``flag_path`` and the
    connection hint. Only the flag's SHA-256 hash is persisted (PRD §20, §49).
    """
    flag_path = lab_cfg["flag_path"]
    flag = generate_lab_flag()
    name = lab.container_name or _container_name(lab)
    container_id, ip = await docker_adapter.create_and_start_container(
        name, lab_cfg["image"], lab.network_name, cmd=_flag_command(flag_path, flag)
    )
    lab.container_id = container_id
    lab.container_name = name
    lab.flag_hash = hash_flag(flag)
    lab.flag_path = flag_path
    lab.connection_hint = (
        f"Container {name} is live at {ip} on isolated network {lab.network_name}. "
        f"The flag for this session is written to {flag_path} inside the container. "
        f"Environment expires in {lab_cfg['expiry_minutes']} minutes."
    )


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
    lab_cfg = _lab_settings(challenge)
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
    cap = lab_cfg.get("max_instances") or settings.lab_max_instances_per_user
    if active >= cap:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Lab limit reached ({cap} active labs at a time). "
                "Stop or reset one first."
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
        await _start_container(lab, lab_cfg)
        lab.status = "running"
        lab.expires_at = datetime.now(UTC) + timedelta(
            minutes=lab_cfg["expiry_minutes"]
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

    challenge = await db.get(Challenge, lab.challenge_id)
    lab_cfg = _lab_settings(challenge)
    if lab.container_id:
        try:
            await docker_adapter.remove_container(lab.container_id)
        except DockerError:
            pass

    try:
        await docker_adapter.ensure_network(lab.network_name)
        await _start_container(lab, lab_cfg)
        lab.status = "running"
        lab.expires_at = datetime.now(UTC) + timedelta(
            minutes=lab_cfg["expiry_minutes"]
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


async def admin_list_labs(
    db: AsyncSession,
    *,
    status_filter: str | None = None,
    user_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[LabAdminOut], int]:
    conditions = []
    if status_filter:
        conditions.append(LabInstance.status == status_filter)
    if user_id:
        conditions.append(LabInstance.user_id == user_id)

    total = int(
        await db.scalar(
            select(func.count()).select_from(LabInstance).where(*conditions)
        )
        or 0
    )
    labs = (
        await db.scalars(
            select(LabInstance)
            .where(*conditions)
            .order_by(LabInstance.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    users = await _users_map(db, [lab.user_id for lab in labs]) if labs else {}
    challenges = (
        {
            c.id: c
            for c in (
                await db.scalars(
                    select(Challenge).where(
                        Challenge.id.in_([lab.challenge_id for lab in labs])
                    )
                )
            ).all()
        }
        if labs
        else {}
    )

    out: list[LabAdminOut] = []
    for lab in labs:
        challenge = challenges.get(lab.challenge_id)
        u = users.get(str(lab.user_id))
        out.append(
            LabAdminOut(
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
                user_id=lab.user_id,
                user_display_name=u["display_name"] if u else None,
                user_email=u["email"] if u else None,
            )
        )
    return out, total


async def admin_terminate_lab(
    db: AsyncSession,
    lab: LabInstance,
    admin_user: User,
    request: Request | None = None,
) -> LabAdminOut:
    if lab.container_id:
        try:
            await docker_adapter.stop_container(lab.container_id)
            await docker_adapter.remove_container(lab.container_id)
        except DockerError:
            pass
    lab.status = "expired"
    await db.commit()
    await db.refresh(lab)
    await record_audit(
        db,
        event="lab.terminate",
        user_id=admin_user.id,
        target_id=str(lab.id),
        request=request,
    )
    u = (await _users_map(db, [lab.user_id])).get(str(lab.user_id))
    challenge = await db.get(Challenge, lab.challenge_id)
    return LabAdminOut(
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
        user_id=lab.user_id,
        user_display_name=u["display_name"] if u else None,
        user_email=u["email"] if u else None,
    )


async def _users_map(
    db: AsyncSession, user_ids: list[uuid.UUID]
) -> dict[str, dict[str, str | None]]:
    if not user_ids:
        return {}
    rows = (
        await db.execute(
            select(User.id, User.display_name, User.email).where(
                User.id.in_(user_ids)
            )
        )
    ).all()
    return {
        str(row[0]): {"display_name": row[1], "email": row[2]} for row in rows
    }