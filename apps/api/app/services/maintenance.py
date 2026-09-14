"""Background maintenance tasks (PRD §18/§44 session monitoring + Track 3 competition scheduler).

A low-frequency sweep:
  - expires overdue labs and fails provisioning-stuck ones,
  - auto-transitions scheduled/live competitions based on time.
"""
from __future__ import annotations

import asyncio
import logging

from app.db.base import SessionLocal
from app.services.competitions import auto_transition_competitions
from app.services.labs import expire_stale_labs

logger = logging.getLogger("cyberlab.maintenance")

SWEEP_INTERVAL_SECONDS = 60


async def lab_maintenance_loop(stop_event: asyncio.Event) -> None:
    """Run the lab expiry/cleanup + competition transition sweep until ``stop_event`` is set."""
    while True:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=SWEEP_INTERVAL_SECONDS)
        except TimeoutError:
            pass
        if stop_event.is_set():
            return
        async with SessionLocal() as db:
            try:
                changed = await expire_stale_labs(db)
            except Exception:
                logger.exception("lab maintenance sweep failed")
                changed = 0
            if changed:
                logger.info("lab maintenance sweep changed %s labs", changed)

            try:
                comp_changed = await auto_transition_competitions(db)
            except Exception:
                logger.exception("competition auto-transition failed")
                comp_changed = 0
            if comp_changed:
                logger.info("auto-transitioned %s competitions", comp_changed)