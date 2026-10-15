"""Celery application entrypoint and configuration (Phase 1).

Celery handles background asynchronous tasks:
- Asynchronous lab provisioning and readiness polling
- Recurring maintenance sweeps (lab expiration and competition state changes)
- Machine template builds and validations
"""

from __future__ import annotations

import os

from celery import Celery

from app.core.config import get_settings

settings = get_settings()
redis_url = os.getenv("CELERY_BROKER_URL", settings.redis_url)
result_backend = os.getenv("CELERY_RESULT_BACKEND", settings.redis_url)

celery_app = Celery(
    "cyberlab",
    broker=redis_url,
    backend=result_backend,
    include=[
        "app.tasks.maintenance",
        "app.tasks.provisioning",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=900,  # 15 minutes max
    beat_schedule={
        "lab-maintenance-sweep-every-minute": {
            "task": "app.tasks.maintenance.maintenance_sweep_task",
            "schedule": 60.0,
        },
    },
)
