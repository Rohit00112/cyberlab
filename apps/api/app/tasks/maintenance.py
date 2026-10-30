"""Periodic maintenance Celery tasks (Phase 1)."""

from __future__ import annotations

import asyncio
import logging

from app.db.base import SessionLocal
from app.services.competitions import auto_transition_competitions
from app.services.labs import expire_stale_labs
from app.services.vpn import reconcile_wireguard_server_peers
from app.tasks.provisioning import redispatch_pending_provisioning_jobs
from app.worker import celery_app

logger = logging.getLogger("cyberlab.tasks.maintenance")


async def _run_maintenance_sweep() -> dict[str, int]:
    async with SessionLocal() as db:
        labs_changed = 0
        comp_changed = 0
        jobs_redispatched = 0
        vpn_checked = 0
        try:
            labs_changed = await expire_stale_labs(db)
        except Exception:
            logger.exception("Celery lab maintenance sweep failed")
            await db.rollback()

        try:
            comp_changed = await auto_transition_competitions(db)
        except Exception:
            logger.exception("Celery competition auto-transition failed")
            await db.rollback()

        try:
            jobs_redispatched = await redispatch_pending_provisioning_jobs()
        except Exception:
            logger.exception("Celery pending provisioning redispatch failed")

        try:
            vpn_checked = await reconcile_wireguard_server_peers(db)
        except Exception:
            logger.exception("Celery WireGuard peer reconciliation failed")
            await db.rollback()

        return {
            "labs_expired": labs_changed,
            "competitions_transitioned": comp_changed,
            "provisioning_jobs_redispatched": jobs_redispatched,
            "vpn_peers_checked": vpn_checked,
        }


@celery_app.task(name="app.tasks.maintenance.maintenance_sweep_task")
def maintenance_sweep_task() -> dict[str, int]:
    """Celery beat task executing recurring lab expiry and competition transitions."""
    return asyncio.run(_run_maintenance_sweep())
