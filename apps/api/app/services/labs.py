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
from app.core.flags import generate_lab_flag, guest_flag_command, hash_flag, lab_flag_command
from app.core.lab_transitions import transition_lab
from app.core.states import ACTIVE_STATES, LabState
from app.infrastructure import docker as docker_adapter
from app.infrastructure.base import LabProvider, LabProviderError
from app.infrastructure.docker import DockerError
from app.infrastructure.factory import get_lab_provider
from app.models.audit_logs import AuditLog
from app.models.challenges import Challenge
from app.models.labs import LabInstance
from app.models.machine_templates import MachineTemplateVersion
from app.models.provisioning import ProvisioningJob
from app.models.users import User
from app.schemas.lab import LabAdminOut, LabOut
from app.services.users import record_audit

ACTIVE_STATUSES = {s.value for s in ACTIVE_STATES}
RUST_TERMINAL_BUSY_STATES = {
    "provisioning", "starting", "resetting", "stopping", "terminating",
}
DOCKER_TIMEOUT = 30


def _lab_settings(
    challenge: Challenge | None,
    template_version: MachineTemplateVersion | None = None,
) -> dict:
    """Resolve effective lab config from the challenge and optional template version."""
    settings = get_settings()
    cfg = (challenge.lab_config or {}) if challenge else {}
    if template_version and template_version.config_snapshot:
        snap = template_version.config_snapshot
        if template_version.image_ref:
            cfg = {**cfg, "image": template_version.image_ref}
        elif snap.get("base_image"):
            cfg = {**cfg, "image": snap["base_image"]}

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


def _lab_provider_for(lab: LabInstance) -> LabProvider:
    """Resolve the provider that owns an existing lab's infrastructure."""
    return get_lab_provider(lab.provider)


def _container_name(lab: LabInstance) -> str:
    return f"lab-{str(lab.user_id)[:8]}-{str(lab.id)[:8]}"


def _flag_command(flag_path: str, flag: str) -> list[str]:
    """Shell command that writes the per-session flag into the container then parks it."""
    return lab_flag_command(flag_path, flag)


async def _start_container(lab: LabInstance, lab_cfg: dict) -> None:
    """Create and start the container, injecting a fresh per-session flag.

    Fills ``container_id``/``container_name``/``flag_hash``/``flag_path`` and the
    connection hint. Only the flag's SHA-256 hash is persisted (PRD §20, §49).
    """
    flag_path = lab_cfg["flag_path"]
    flag = generate_lab_flag()
    name = lab.container_name or _container_name(lab)
    provider = get_lab_provider()
    vm_provider = get_settings().lab_provider in {"proxmox", "libvirt"}
    provider_ref, ip = await provider.create_lab(
        name, lab_cfg["image"], lab.network_name,
        cmd=guest_flag_command(flag_path, flag) if vm_provider else _flag_command(flag_path, flag),
    )
    settings = get_settings()
    lab.provider = settings.lab_provider
    lab.provider_ref = provider_ref
    lab.container_id = provider_ref
    lab.container_name = name
    lab.flag_hash = hash_flag(flag)
    lab.flag_path = flag_path
    lab.connection_hint = (
        f"Container {name} is live at {ip} on isolated network {lab.network_name}. "
        f"The flag for this session is written to {flag_path} inside the container. "
        f"Environment expires in {lab_cfg['expiry_minutes']} minutes."
    )


async def _to_out(
    db: AsyncSession, lab: LabInstance, job_id: uuid.UUID | None = None
) -> LabOut:
    await db.refresh(lab)
    challenge = await db.get(Challenge, lab.challenge_id)
    time_remaining: int | None = None
    if lab.expires_at:
        now = datetime.now(UTC)
        exp = lab.expires_at if lab.expires_at.tzinfo else lab.expires_at.replace(tzinfo=UTC)
        time_remaining = max(0, int((exp - now).total_seconds()))

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
        job_id=job_id,
        time_remaining_seconds=time_remaining,
    )


def _network_name(user_id: uuid.UUID) -> str:
    return f"cyberlab-{str(user_id)[:8]}"


async def launch_lab(
    db: AsyncSession,
    user: CurrentUser,
    challenge: Challenge,
    *,
    sync: bool = True,
    idempotency_key: str | None = None,
    request: Request | None = None,
) -> LabOut:
    if not challenge.environment_type or challenge.environment_type == "none":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This challenge does not provide a lab environment.",
        )

    # Serialize launches for one user across API workers and processes. This
    # row lock stays held until the lab (and async job) have been committed;
    # checking counts without a lock allowed concurrent requests to exceed
    # quotas or create duplicate active labs for the same challenge.
    locked_user = await db.scalar(
        select(User.id).where(User.id == user.id).with_for_update()
    )
    if locked_user is None:
        raise HTTPException(status_code=403, detail="User not found")

    # 1. Idempotency guard: Return existing active lab if one is already running/provisioning
    existing = (
        await db.scalars(
            select(LabInstance).where(
                LabInstance.user_id == user.id,
                LabInstance.challenge_id == challenge.id,
                LabInstance.status.in_(ACTIVE_STATUSES),
            )
        )
    ).first()
    if existing:
        existing_job = await db.scalar(
            select(ProvisioningJob.id)
            .where(ProvisioningJob.lab_instance_id == existing.id)
            .order_by(ProvisioningJob.created_at.desc())
            .limit(1)
        )
        result = await _to_out(db, existing, job_id=existing_job)
        await db.commit()  # Release the per-user launch lock.
        return result

    settings = get_settings()
    template_ver = None
    if getattr(challenge, "template_version_id", None):
        template_ver = await db.get(MachineTemplateVersion, challenge.template_version_id)
    lab_cfg = _lab_settings(challenge, template_ver)

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

    # If asynchronous launch requested:
    if not sync:
        lab = LabInstance(
            user_id=user.id,
            challenge_id=challenge.id,
            status=LabState.QUEUED.value,
            network_name=_network_name(user.id),
        )
        db.add(lab)
        await db.flush()

        job = ProvisioningJob(
            lab_instance_id=lab.id,
            user_id=user.id,
            challenge_id=challenge.id,
            idempotency_key=idempotency_key,
            status="pending",
            config=lab_cfg,
        )
        db.add(job)
        # The job and lab must become visible together. A second request
        # must never discover a queued lab without its durable job record.
        await db.commit()
        await db.refresh(job)

        try:
            from app.tasks.provisioning import provision_lab_task
            t = provision_lab_task.delay(str(job.id))
            job.celery_task_id = t.id
            await db.commit()
        except Exception:
            # Leave the committed job pending. The periodic maintenance task
            # retries dispatch after Redis/Celery recovers. An in-process
            # asyncio task is lost whenever this API worker restarts.
            import logging

            logging.getLogger("cyberlab.services.labs").exception(
                "Provisioning dispatch failed for job %s; pending for retry", job.id
            )

        await record_audit(
            db,
            event="lab.launch_queued",
            user_id=user.id,
            target_id=challenge.slug,
            request=request,
        )
        return await _to_out(db, lab, job_id=job.id)

    # Synchronous launch (default for backward compatibility)
    lab = LabInstance(
        user_id=user.id,
        challenge_id=challenge.id,
        status=LabState.PROVISIONING.value,
        network_name=_network_name(user.id),
    )
    db.add(lab)
    await db.commit()
    await db.refresh(lab)

    try:
        provider = get_lab_provider()
        await provider.ensure_network(lab.network_name)
        lab.status = (await transition_lab(lab.status, LabState.STARTING)).value
        await db.commit()
        await _start_container(lab, lab_cfg)
        lab.status = (await transition_lab(lab.status, LabState.RUNNING)).value
        lab.expires_at = datetime.now(UTC) + timedelta(
            minutes=lab_cfg["expiry_minutes"]
        )
    except (DockerError, LabProviderError) as exc:
        try:
            lab.status = (await transition_lab(lab.status, LabState.FAILED)).value
        except Exception:
            lab.status = "error"
        lab.error_message = str(exc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Lab provisioning failed — infrastructure unavailable: {exc}",
        ) from None
    except Exception as exc:
        try:
            lab.status = (await transition_lab(lab.status, LabState.FAILED)).value
        except Exception:
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


async def _can_manage_lab(user: CurrentUser, lab: LabInstance) -> bool:
    from app.core.authorization import check_permission

    return lab.user_id == user.id or await check_permission(user.roles, "lab.admin")


async def stop_lab(
    db: AsyncSession,
    user: CurrentUser,
    lab: LabInstance,
    *,
    request: Request | None = None,
) -> LabOut:
    if not await _can_manage_lab(user, lab):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    ref = lab.provider_ref or lab.container_id
    if lab.status == "running" and not ref:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lab provider reference is missing",
        )
    if get_settings().rust_core_url:
        from app.core.rust_engine import finalize_lab_stop_in_rust

        lab_id = lab.id
        if lab.status == LabState.RUNNING.value and ref:
            try:
                await _lab_provider_for(lab).stop_lab(ref)
            except (DockerError, LabProviderError) as exc:
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Unable to stop lab environment",
                ) from exc
        # Discard the ORM snapshot before the Rust row lock and status/audit
        # transaction. A concurrent reset may have replaced the provider ref.
        await db.rollback()
        await finalize_lab_stop_in_rust(
            str(lab_id), str(user.id), user.roles,
            request.client.host if request and request.client else None, ref,
        )
        refreshed = await db.get(LabInstance, lab_id)
        if refreshed is None:
            raise HTTPException(status_code=404, detail="Lab not found")
        return await _to_out(db, refreshed)
    if lab.status in (LabState.RUNNING.value, "running") and ref:
        try:
            lab.status = (await transition_lab(lab.status, LabState.STOPPING)).value
            await _lab_provider_for(lab).stop_lab(ref)
        except (DockerError, LabProviderError) as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to stop lab environment",
            ) from exc
    try:
        lab.status = (await transition_lab(lab.status, LabState.STOPPED)).value
    except Exception:
        lab.status = "stopped"
    db.add(AuditLog(
        event="lab.stop", user_id=user.id, target_id=str(lab.id),
        ip_address=request.client.host if request and request.client else None,
    ))
    await db.commit()
    return await _to_out(db, lab)


async def _reset_lab_with_rust(
    db: AsyncSession,
    user: CurrentUser,
    lab: LabInstance,
    lab_cfg: dict,
    request: Request | None,
) -> LabOut:
    """Claim reset before provider I/O; finalize state, lease and audit in Rust."""
    from app.core.rust_engine import transition_lab_reset_in_rust

    lab_id = lab.id
    old_ref = lab.provider_ref or lab.container_id
    old_provider = _lab_provider_for(lab)
    new_provider = get_lab_provider()
    network_name = lab.network_name
    prepared = LabInstance(
        id=lab_id, user_id=lab.user_id, challenge_id=lab.challenge_id,
        network_name=network_name, container_name=lab.container_name,
    )
    identity = {
        "lab_id": str(lab_id),
        "actor_id": str(user.id),
        "roles": user.roles,
        "ip_address": request.client.host if request and request.client else None,
        "expected_old_ref": old_ref,
    }
    # Do not carry a stale ORM read transaction over the Rust row lock.
    await db.rollback()
    await transition_lab_reset_in_rust("begin", **identity)
    old_removed = old_ref is None
    new_ref: str | None = None
    try:
        if old_ref:
            # An uncertain old-resource removal must never be ignored.
            await old_provider.remove_lab(old_ref)
            old_removed = True
        await new_provider.ensure_network(network_name)
        await _start_container(prepared, lab_cfg)
        new_ref = prepared.provider_ref
        await transition_lab_reset_in_rust(
            "complete", **identity,
            provider=prepared.provider,
            provider_ref=new_ref,
            container_name=prepared.container_name,
            flag_hash=prepared.flag_hash,
            flag_path=prepared.flag_path,
            connection_hint=prepared.connection_hint,
            expiry_minutes=lab_cfg["expiry_minutes"],
        )
    except Exception as exc:
        # The core may have committed before its response was lost. Check
        # persisted state before compensating a potentially live replacement.
        await db.rollback()
        if new_ref:
            current = await db.get(LabInstance, lab_id)
            if (
                current is not None
                and current.status == "running"
                and current.provider_ref == new_ref
            ):
                return await _to_out(db, current)
        await db.rollback()

        remaining = old_ref if not old_removed else None
        allocated = new_ref or (exc.provider_ref if isinstance(exc, LabProviderError) else None)
        if allocated:
            try:
                await new_provider.stop_lab(allocated)
            except (DockerError, LabProviderError):
                pass
            try:
                await new_provider.remove_lab(allocated)
            except (DockerError, LabProviderError):
                remaining = allocated
        try:
            await transition_lab_reset_in_rust(
                "fail", **identity, error_message=str(exc)[:4096] or "Reset failed",
                remaining_provider_ref=remaining,
            )
        except Exception:
            import logging

            logging.getLogger("cyberlab.services.labs").exception(
                "Reset %s could not record failure after provider compensation", lab_id,
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lab reset failed — infrastructure or persistence unavailable",
        ) from exc
    await db.rollback()
    refreshed = await db.get(LabInstance, lab_id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    return await _to_out(db, refreshed)


async def reset_lab(
    db: AsyncSession,
    user: CurrentUser,
    lab: LabInstance,
    *,
    request: Request | None = None,
) -> LabOut:
    if not await _can_manage_lab(user, lab):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    challenge = await db.get(Challenge, lab.challenge_id)
    template_ver = None
    if getattr(challenge, "template_version_id", None):
        template_ver = await db.get(MachineTemplateVersion, challenge.template_version_id)
    lab_cfg = _lab_settings(challenge, template_ver)
    if get_settings().rust_core_url:
        return await _reset_lab_with_rust(db, user, lab, lab_cfg, request)
    provider = get_lab_provider()
    ref = lab.provider_ref or lab.container_id
    if ref:
        try:
            await _lab_provider_for(lab).remove_lab(ref)
        except (DockerError, LabProviderError):
            pass

    try:
        lab.status = (await transition_lab(lab.status, LabState.RESETTING)).value
        await db.commit()
        lab.status = (await transition_lab(lab.status, LabState.PROVISIONING)).value
        await db.commit()
        await provider.ensure_network(lab.network_name)
        lab.status = (await transition_lab(lab.status, LabState.STARTING)).value
        await db.commit()
        await _start_container(lab, lab_cfg)
        lab.status = (await transition_lab(lab.status, LabState.RUNNING)).value
        lab.expires_at = datetime.now(UTC) + timedelta(
            minutes=lab_cfg["expiry_minutes"]
        )
        lab.error_message = None
    except (DockerError, LabProviderError) as exc:
        try:
            lab.status = (await transition_lab(lab.status, LabState.FAILED)).value
        except Exception:
            lab.status = "error"
        lab.error_message = str(exc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Lab reset failed — infrastructure unavailable: {exc}",
        ) from None
    except Exception as exc:
        try:
            lab.status = (await transition_lab(lab.status, LabState.FAILED)).value
        except Exception:
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


async def extend_lab(
    db: AsyncSession,
    user: CurrentUser,
    lab: LabInstance,
    additional_minutes: int = 30,
    *,
    request: Request | None = None,
) -> LabOut:
    if not await _can_manage_lab(user, lab):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    settings = get_settings()
    if settings.rust_core_url:
        from app.core.rust_engine import extend_lab_in_rust

        lab_id = lab.id
        # Recheck ownership, live state and lease bounds against the database
        # under a Rust-held row lock; commit the mutation with its audit.
        await db.rollback()
        await extend_lab_in_rust(
            str(lab_id), str(user.id), user.roles,
            request.client.host if request and request.client else None,
            max(5, min(additional_minutes, 120)),
            settings.lab_max_expiry_minutes,
        )
        refreshed = await db.get(LabInstance, lab_id)
        if refreshed is None:
            raise HTTPException(status_code=404, detail="Lab not found")
        return await _to_out(db, refreshed)
    if lab.status not in (LabState.RUNNING.value, "running"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot extend lab in status '{lab.status}' (must be running)",
        )
    now = datetime.now(UTC)
    current_exp = lab.expires_at if lab.expires_at else now
    if current_exp.tzinfo is None:
        current_exp = current_exp.replace(tzinfo=UTC)
    if now > current_exp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot extend an already expired lab. Please reset or relaunch.",
        )
    added = max(5, min(additional_minutes, 120))
    new_expires = current_exp + timedelta(minutes=added)
    created = lab.created_at or now
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    max_allowed = created + timedelta(minutes=settings.lab_max_expiry_minutes)
    if new_expires > max_allowed:
        new_expires = max_allowed
    lab.expires_at = new_expires
    await db.commit()
    await db.refresh(lab)
    await record_audit(
        db, event="lab.extend", user_id=user.id, target_id=str(lab.id), request=request
    )
    return await _to_out(db, lab)


async def expire_lab(
    db: AsyncSession,
    user: CurrentUser,
    lab: LabInstance,
    *,
    request: Request | None = None,
) -> LabOut:
    if not await _can_manage_lab(user, lab):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    rust_enabled = bool(get_settings().rust_core_url)
    if rust_enabled and lab.status in RUST_TERMINAL_BUSY_STATES:
        raise HTTPException(
            status_code=409, detail=f"Cannot expire lab in status '{lab.status}'",
        )
    ref = lab.provider_ref or lab.container_id
    if lab.status == "running" and not ref:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lab provider reference is missing",
        )
    if lab.status == "running" and ref:
        try:
            await _lab_provider_for(lab).stop_lab(ref)
        except (DockerError, LabProviderError) as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to stop lab environment",
            ) from exc
    if rust_enabled:
        from app.core.rust_engine import finalize_lab_terminal_in_rust

        lab_id = lab.id
        await db.rollback()
        await finalize_lab_terminal_in_rust(
            "expire", str(lab_id), str(user.id), user.roles,
            request.client.host if request and request.client else None, ref,
        )
        refreshed = await db.get(LabInstance, lab_id)
        if refreshed is None:
            raise HTTPException(status_code=404, detail="Lab not found")
        return await _to_out(db, refreshed)
    lab.status = "expired"
    db.add(AuditLog(
        event="lab.expire", user_id=user.id, target_id=str(lab.id),
        ip_address=request.client.host if request and request.client else None,
    ))
    await db.commit()
    return await _to_out(db, lab)


async def expire_stale_labs(db: AsyncSession) -> int:
    """Expire overdue running labs and fail provisioning-stuck labs.

    Returns the number of labs whose status changed. Called by read paths and
    by the background maintenance sweep (PRD §18 "every environment must have
    an expiration time", §44 session monitoring). Containers are stopped but
    deliberately not removed — a later destroy pass or admin terminate cleans up.
    """
    changed = 0
    now = datetime.now(UTC)
    settings = get_settings()
    rows = (await db.scalars(select(LabInstance))).all()
    if settings.rust_core_url:
        from app.core.rust_engine import finalize_automatic_lab_expiry_in_rust

        # Copy all required ORM/provider fields before closing the read
        # transaction: SQLAlchemy expires ORM snapshots after rollback.
        due = []
        for lab in rows:
            if (
                lab.status == "running"
                and lab.expires_at
                and now > lab.expires_at.replace(tzinfo=UTC)
            ):
                ref = lab.provider_ref or lab.container_id
                if ref:
                    due.append((str(lab.id), ref, _lab_provider_for(lab)))
        await db.rollback()
        for lab_id, ref, provider in due:
            try:
                await provider.stop_lab(ref)
            except (DockerError, LabProviderError):
                # The caller can safely retry on the next sweep.
                continue
            if await finalize_automatic_lab_expiry_in_rust(lab_id, ref):
                changed += 1
        # Provisioning timeouts still use their own Python transaction. Reload
        # only those rows, instead of touching rollback-expired ORM snapshots.
        rows = (
            await db.scalars(
                select(LabInstance).where(LabInstance.status == "provisioning")
            )
        ).all()
    for lab in rows:
        if (
            lab.status == "running"
            and lab.expires_at
            and now > lab.expires_at.replace(tzinfo=UTC)
        ):
            ref = lab.provider_ref or lab.container_id
            if not ref:
                # A running environment without a provider handle cannot be
                # proven stopped. Keep it visible for operator recovery.
                continue
            try:
                await _lab_provider_for(lab).stop_lab(ref)
            except (DockerError, LabProviderError):
                # Never claim a remote environment has expired when its
                # provider refused to stop it. Retry on the next sweep.
                continue
            lab.status = "expired"
            db.add(AuditLog(
                event="lab.expire_auto", user_id=lab.user_id, target_id=str(lab.id),
            ))
            changed += 1
        elif lab.status == "provisioning" and lab.created_at:
            active_job = await db.scalar(
                select(ProvisioningJob)
                .where(
                    ProvisioningJob.lab_instance_id == lab.id,
                    ProvisioningJob.status == "running",
                )
                .order_by(ProvisioningJob.created_at.desc())
                .limit(1)
                .with_for_update()
            )
            current_lab = await db.scalar(
                select(LabInstance)
                .where(LabInstance.id == lab.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if current_lab is None or current_lab.status != "provisioning":
                # The worker may have advanced the lab while this sweep waited
                # for its job lock. Never overwrite a newer state.
                continue
            lab = current_lab
            # A lab may wait queued for hours before its job is claimed.
            # Timeout from the actual claim, not the original request.
            since = (active_job.started_at if active_job else None) or lab.created_at
            if now - since.replace(tzinfo=UTC) > timedelta(
                minutes=settings.lab_provisioning_timeout_minutes
            ):
                lab.status = LabState.FAILED.value
                lab.error_message = "Provisioning timed out."
                if active_job:
                    active_job.status = "failed"
                    active_job.completed_at = now
                    active_job.error_message = "Provisioning timed out."
                db.add(AuditLog(
                    event="lab.provisioning_timeout", user_id=lab.user_id,
                    target_id=str(lab.id),
                    details={"job_id": str(active_job.id)} if active_job else None,
                ))
                changed += 1
    if changed:
        await db.commit()
    return changed


async def my_labs(db: AsyncSession, user: CurrentUser) -> list[LabOut]:
    await expire_stale_labs(db)
    rows = (
        await db.scalars(
            select(LabInstance)
            .where(LabInstance.user_id == user.id)
            .order_by(LabInstance.created_at.desc())
        )
    ).all()

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
    from app.core.authorization import check_permission

    # Protect the destructive provider call even if an internal caller bypasses
    # the public route's require_permission dependency.
    if not await check_permission(admin_user.roles or [], "lab.admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    rust_enabled = bool(get_settings().rust_core_url)
    if rust_enabled and lab.status in RUST_TERMINAL_BUSY_STATES:
        raise HTTPException(
            status_code=409, detail=f"Cannot terminate lab in status '{lab.status}'",
        )
    ref = lab.provider_ref or lab.container_id
    if lab.status == "running" and not ref:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lab provider reference is missing",
        )
    if ref:
        provider = _lab_provider_for(lab)
        try:
            await provider.stop_lab(ref)
            await provider.remove_lab(ref)
        except (DockerError, LabProviderError) as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to terminate lab environment",
            ) from exc
    if rust_enabled:
        from app.core.rust_engine import finalize_lab_terminal_in_rust

        lab_id = lab.id
        await db.rollback()
        await finalize_lab_terminal_in_rust(
            "terminate", str(lab_id), str(admin_user.id), admin_user.roles or [],
            request.client.host if request and request.client else None, ref,
        )
        lab = await db.get(LabInstance, lab_id)
        if lab is None:
            raise HTTPException(status_code=404, detail="Lab not found")
    else:
        lab.status = "expired"
        db.add(AuditLog(
            event="lab.terminate", user_id=admin_user.id, target_id=str(lab.id),
            ip_address=request.client.host if request and request.client else None,
        ))
        await db.commit()
        await db.refresh(lab)
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


async def lab_provider_status(
    db: AsyncSession,
    user: CurrentUser,
    lab: LabInstance,
) -> dict:
    """Return real-time status from the lab's infrastructure provider."""
    if not await _can_manage_lab(user, lab):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    ref = lab.provider_ref or lab.container_id
    if not ref:
        return {"status": lab.status, "provider": lab.provider, "detail": "no provider ref"}

    provider = _lab_provider_for(lab)
    result = await provider.lab_status(ref)
    result["lab_id"] = str(lab.id)
    result["provider"] = lab.provider
    return result


async def lab_provider_logs(
    db: AsyncSession,
    user: CurrentUser,
    lab: LabInstance,
    *,
    tail: int = 100,
) -> dict:
    """Return recent logs from the lab's infrastructure provider."""
    if not await _can_manage_lab(user, lab):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    ref = lab.provider_ref or lab.container_id
    if not ref:
        return {"logs": "", "detail": "no provider ref"}

    provider = _lab_provider_for(lab)
    logs = await provider.lab_logs(ref, tail=tail)
    return {"lab_id": str(lab.id), "provider": lab.provider, "logs": logs}
