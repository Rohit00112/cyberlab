"""Background provisioning task runner (Phase 1)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from app.core.flags import generate_lab_flag, hash_flag
from app.core.states import LabState, transition
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
        job = await db.get(ProvisioningJob, job_uuid)
        if not job:
            logger.error("ProvisioningJob %s not found", job_uuid)
            return False

        lab = await db.get(LabInstance, job.lab_instance_id)
        challenge = await db.get(Challenge, job.challenge_id)
        if not lab or not challenge:
            job.status = "failed"
            job.error_details = {"error": "Associated lab or challenge record missing"}
            await db.commit()
            return False

        job.status = "running"
        job.started_at = datetime.now(UTC)
        try:
            lab.status = transition(lab.status, LabState.PROVISIONING).value
        except Exception:
            lab.status = LabState.PROVISIONING.value
        await db.commit()

        try:
            cfg = job.config or {}
            flag_path = cfg.get("flag_path", "/flag.txt")
            image = cfg.get("image", "alpine:3.20")
            expiry_minutes = cfg.get("expiry_minutes", 60)

            # Start container via provider
            provider = get_lab_provider(lab.provider)
            await provider.ensure_network(lab.network_name)

            flag = generate_lab_flag()
            cmd = ["/bin/sh", "-c", f"printf '%s\\n' '{flag}' > {flag_path} && sleep infinity"]
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
            lab.status = LabState.RUNNING.value
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
            job.error_details = {"error": str(exc)}
            await db.commit()
            return False


@celery_app.task(name="app.tasks.provisioning.provision_lab_task", bind=True, max_retries=2)
def provision_lab_task(self, job_id_str: str) -> bool:
    """Asynchronous Celery task for lab provisioning."""
    try:
        return asyncio.run(execute_provisioning_job(job_id_str))
    except Exception as exc:
        logger.exception("provision_lab_task unhandled exception: %s", exc)
        raise self.retry(exc=exc, countdown=10) from exc
