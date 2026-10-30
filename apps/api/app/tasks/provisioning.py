"""Background provisioning task runner (Phase 1)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.flags import generate_lab_flag, hash_flag, lab_flag_command
from app.core.lab_transitions import transition_lab
from app.core.states import LabState
from app.db.base import SessionLocal
from app.infrastructure.factory import get_lab_provider
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
            job.status = "failed"
            job.error_message = "Associated lab or challenge record missing"
            await db.commit()
            return False

        if rust_managed and lab.status != LabState.PROVISIONING.value:
            # A concurrent stop/terminate after claim must prevent provider I/O.
            logger.warning("Lab %s changed state after Rust job claim", lab.id)
            return False

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
            lab.status = (await transition_lab(lab.status, LabState.STARTING)).value
            await db.commit()

            flag = generate_lab_flag()
            cmd = lab_flag_command(flag_path, flag)
            container_name = lab.container_name or f"lab-{str(lab.user_id)[:8]}-{str(lab.id)[:8]}"

            provider_ref, ip = await provider.create_lab(
                container_name, image, lab.network_name, cmd=cmd
            )

            lab.provider_ref = provider_ref
            lab.container_id = provider_ref
            lab.container_name = container_name
            lab.flag_hash = hash_flag(flag)
            lab.flag_path = flag_path
            lab.connection_hint = (
                f"Target {container_name} is running at {ip} on network {lab.network_name}. "
                f"Flag location: {flag_path}. Lease valid for {expiry_minutes} minutes."
            )
            lab.status = (await transition_lab(lab.status, LabState.RUNNING)).value
            lab.expires_at = datetime.now(UTC) + timedelta(minutes=expiry_minutes)

            job.status = "completed"
            job.completed_at = datetime.now(UTC)
            await db.commit()
            logger.info("Successfully provisioned lab %s (job %s)", lab.id, job.id)
            return True

        except Exception as exc:
            logger.exception("Provisioning failed for lab %s (job %s)", lab.id, job.id)
            lab.status = LabState.FAILED.value
            lab.error_message = str(exc)
            job.status = "failed"
            job.completed_at = datetime.now(UTC)
            job.error_message = str(exc)
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
