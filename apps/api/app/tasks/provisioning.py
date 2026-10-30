"""Background provisioning task runner (Phase 1)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import get_settings
from app.core.flags import generate_lab_flag, guest_flag_command, hash_flag, lab_flag_command
from app.core.lab_transitions import transition_lab
from app.core.states import LabState
from app.db.base import SessionLocal
from app.infrastructure.factory import get_lab_provider
from app.models.audit_logs import AuditLog
from app.models.challenges import Challenge
from app.models.labs import LabInstance
from app.models.provisioning import ProvisioningJob
from app.worker import celery_app

logger = logging.getLogger("cyberlab.tasks.provisioning")


async def execute_provisioning_job(job_id_str: str) -> bool:
    """Core provisioning routine executed either via Celery or inline."""
    job_uuid = uuid.UUID(job_id_str)
    async with SessionLocal() as db:
        rust_managed = bool(get_settings().rust_core_url)
        if rust_managed:
            from app.core.rust_engine import claim_provisioning_job_in_rust

            # Fail closed: Rust owns both the job claim and queued lab status
            # before Python touches any provider. Duplicate delivery skips I/O.
            if not await claim_provisioning_job_in_rust(str(job_uuid)):
                return False
            job = await db.get(ProvisioningJob, job_uuid)
        else:
            # Standalone Python fallback preserves the original job claim.
            job = await db.scalar(
                select(ProvisioningJob)
                .where(ProvisioningJob.id == job_uuid, ProvisioningJob.status == "pending")
                .with_for_update(skip_locked=True)
            )
            if job:
                job.status = "running"
                job.started_at = datetime.now(UTC)
                await db.commit()
        if not job:
            logger.info("ProvisioningJob %s is missing, claimed or already processed", job_uuid)
            return False
        if rust_managed and job.status != "running":
            logger.error("Rust claim for job %s did not persist its running state", job_uuid)
            return False

        lab = await db.get(LabInstance, job.lab_instance_id)
        challenge = await db.get(Challenge, job.challenge_id)
        if not lab or not challenge:
            if rust_managed:
                from app.core.rust_engine import fail_provisioning_job_in_rust

                await db.rollback()
                await fail_provisioning_job_in_rust(
                    job_id=str(job_uuid),
                    error_message="Associated lab or challenge record missing",
                    cleanup_failed=False, provider_ref=None,
                )
                return False
            job.status = "failed"
            job.error_message = "Associated lab or challenge record missing"
            await db.commit()
            return False

        if rust_managed and lab.status != LabState.PROVISIONING.value:
            # A concurrent stop/terminate after claim must prevent provider I/O.
            logger.warning("Lab %s changed state after Rust job claim", lab.id)
            return False

        created_ref: str | None = None
        provider = None
        lab_id = lab.id
        try:
            if not rust_managed:
                # Keep the original transition guard in the Python fallback;
                # only Rust claims have already applied queued -> provisioning.
                lab.status = (await transition_lab(lab.status, LabState.PROVISIONING)).value
                await db.commit()
            cfg = job.config or {}
            flag_path = cfg.get("flag_path", "/flag.txt")
            image = cfg.get("image", "alpine:3.20")
            expiry_minutes = cfg.get("expiry_minutes", 60)

            # Start container via provider
            provider = get_lab_provider(lab.provider)
            await provider.ensure_network(lab.network_name)
            if rust_managed:
                from app.core.rust_engine import start_provisioning_job_in_rust

                # Release the ORM read transaction before Rust locks the rows.
                # An outdated worker cannot revive a stopped lab.
                await db.rollback()
                if not await start_provisioning_job_in_rust(str(job_uuid)):
                    return False
                await db.refresh(lab)
                await db.refresh(job)
            else:
                # A maintenance sweep may have failed this job while the
                # provider network was being prepared. Recheck authoritative
                # state under row locks before launching an environment.
                await db.rollback()
                # Match the Rust/maintenance lock order: job, then lab.
                job = await db.scalar(
                    select(ProvisioningJob)
                    .where(ProvisioningJob.id == job_uuid)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                lab = await db.scalar(
                    select(LabInstance)
                    .where(LabInstance.id == lab_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if (
                    lab is None or job is None
                    or lab.status != LabState.PROVISIONING.value
                    or job.status != "running"
                ):
                    await db.rollback()
                    return False
                lab.status = (await transition_lab(lab.status, LabState.STARTING)).value
                await db.commit()

            flag = generate_lab_flag()
            cmd = (
                guest_flag_command(flag_path, flag)
                if lab.provider in {"proxmox", "libvirt"}
                else lab_flag_command(flag_path, flag)
            )
            container_name = lab.container_name or f"lab-{str(lab.user_id)[:8]}-{str(lab.id)[:8]}"

            provider_ref, ip = await provider.create_lab(
                container_name, image, lab.network_name, cmd=cmd
            )
            created_ref = provider_ref

            connection_hint = (
                f"Target {container_name} is running at {ip} on network {lab.network_name}. "
                f"Flag location: {flag_path}. Lease valid for {expiry_minutes} minutes."
            )
            if rust_managed:
                from app.core.rust_engine import complete_provisioning_job_in_rust

                await db.rollback()
                if not await complete_provisioning_job_in_rust(
                    job_id=str(job_uuid),
                    provider_ref=provider_ref, container_name=container_name,
                    flag_hash=hash_flag(flag), flag_path=flag_path,
                    connection_hint=connection_hint, expiry_minutes=expiry_minutes,
                ):
                    raise RuntimeError("Rust rejected stale provisioning completion")
            else:
                lab.provider_ref = provider_ref
                lab.container_id = provider_ref
                lab.container_name = container_name
                lab.flag_hash = hash_flag(flag)
                lab.flag_path = flag_path
                lab.connection_hint = connection_hint
                lab.status = (await transition_lab(lab.status, LabState.RUNNING)).value
                lab.expires_at = datetime.now(UTC) + timedelta(minutes=expiry_minutes)
                job.status = "completed"
                job.completed_at = datetime.now(UTC)
                await db.commit()
            logger.info("Successfully provisioned lab %s (job %s)", lab_id, job_uuid)
            return True

        except HTTPException:
            # A Rust outage is not a provider failure. Keep its durable job
            # state intact for operator recovery instead of writing around it.
            await db.rollback()
            if created_ref is not None and provider is not None:
                # The DB transaction may have committed before the HTTP reply
                # was lost. Check authoritative state before compensating.
                persisted_job = await db.get(ProvisioningJob, job_uuid)
                persisted_lab = await db.get(LabInstance, lab_id)
                if (
                    persisted_job is not None and persisted_lab is not None
                    and persisted_job.status == "completed"
                    and persisted_lab.status == LabState.RUNNING.value
                    and persisted_lab.provider_ref == created_ref
                ):
                    logger.warning(
                        "Rust completion reply lost; verified committed lab=%s job=%s",
                        lab_id, job_uuid,
                    )
                    return True
                await db.rollback()
                try:
                    await provider.stop_lab(created_ref)
                    await provider.remove_lab(created_ref)
                except Exception:
                    logger.critical(
                        "MANUAL RECOVERY REQUIRED: Rust completion failed and provider "
                        "cleanup failed for lab=%s job=%s provider_ref=%s",
                        lab_id, job_uuid, created_ref, exc_info=True,
                    )
            raise
        except Exception as exc:
            logger.exception("Provisioning failed for lab %s (job %s)", lab_id, job_uuid)
            await db.rollback()
            # A provider can allocate a VM/container before raising, without
            # returning the normal (ref, IP) tuple to this worker.
            created_ref = created_ref or getattr(exc, "provider_ref", None)
            cleanup_error: str | None = None
            if created_ref is not None and provider is not None:
                try:
                    await provider.stop_lab(created_ref)
                    await provider.remove_lab(created_ref)
                except Exception as cleanup_exc:
                    # Persist the provider handle for an administrator. A
                    # failed cleanup must never silently orphan a live lab.
                    logger.exception(
                        "Provider cleanup failed for lab %s (%s)", lab_id, created_ref
                    )
                    cleanup_error = str(cleanup_exc)
            if rust_managed:
                from app.core.rust_engine import fail_provisioning_job_in_rust

                message = str(exc)
                if cleanup_error:
                    message += f"; provider cleanup failed: {cleanup_error}"
                try:
                    persisted = await fail_provisioning_job_in_rust(
                        job_id=str(job_uuid), error_message=message[:4096],
                        cleanup_failed=cleanup_error is not None,
                        provider_ref=created_ref if cleanup_error else None,
                    )
                    if not persisted:
                        logger.warning(
                            "Stale Rust provisioning failure for job=%s lab=%s",
                            job_uuid, lab_id,
                        )
                except Exception:
                    logger.critical(
                        "MANUAL RECOVERY REQUIRED: Rust failure transaction unavailable; "
                        "job=%s lab=%s provider_ref=%s cleanup_failed=%s",
                        job_uuid, lab_id, created_ref, bool(cleanup_error),
                        exc_info=True,
                    )
                    raise
                return False
            lab = await db.get(LabInstance, lab_id)
            job = await db.get(ProvisioningJob, job_uuid)
            if lab is None or job is None:
                logger.error("Provisioning failure could not load lab/job %s", job_uuid)
                return False
            lab.status = LabState.FAILED.value
            lab.error_message = str(exc)
            if cleanup_error:
                lab.provider_ref = created_ref
                lab.container_id = created_ref
                lab.error_message += f"; provider cleanup failed: {cleanup_error}"
            job.status = "failed"
            job.completed_at = datetime.now(UTC)
            job.error_message = lab.error_message
            db.add(AuditLog(
                event="lab.provisioning.failure", user_id=lab.user_id,
                target_id=str(lab.id),
                details={"cleanup_failed": cleanup_error is not None},
            ))
            await db.commit()
            return False


async def redispatch_pending_provisioning_jobs(*, limit: int = 50) -> int:
    """Retry broker delivery of durable pending jobs after a transient outage.

    A job is claimed for execution by the worker, not by this dispatcher.
    This makes duplicate dispatch safe even if maintenance runs concurrently.
    """
    async with SessionLocal() as db:
        job_ids = (
            await db.scalars(
                select(ProvisioningJob.id)
                .where(ProvisioningJob.status == "pending")
                .order_by(ProvisioningJob.created_at.asc())
                .limit(limit)
            )
        ).all()

    dispatched = 0
    for job_id in job_ids:
        try:
            result = provision_lab_task.delay(str(job_id))
        except Exception:
            logger.exception("Could not redispatch provisioning job %s", job_id)
            continue
        # No need to hold DB locks across broker I/O. If the task already
        # claimed the job it is no longer pending, so this update is advisory.
        async with SessionLocal() as db:
            job = await db.get(ProvisioningJob, job_id)
            if job is not None and job.status == "pending":
                job.celery_task_id = result.id
                await db.commit()
        dispatched += 1
    return dispatched


@celery_app.task(name="app.tasks.provisioning.provision_lab_task", bind=True, max_retries=2)
def provision_lab_task(self, job_id_str: str) -> bool:
    """Asynchronous Celery task for lab provisioning."""
    try:
        return asyncio.run(execute_provisioning_job(job_id_str))
    except Exception as exc:
        logger.exception("provision_lab_task unhandled exception: %s", exc)
        raise self.retry(exc=exc, countdown=10) from exc
