"""Provisioning job and compute infrastructure models.

ProvisioningJob is a durable record of asynchronous provisioning work.
ComputeNode tracks registered compute hosts and their capacity.
ResourceReservation pre-allocates resources before provisioning.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProvisioningJob(Base):
    """Durable record of an asynchronous lab provisioning request."""

    __tablename__ = "provisioning_jobs"
    __table_args__ = (
        Index("ix_provisioning_jobs_status", "status"),
        Index("ix_provisioning_jobs_lab", "lab_instance_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lab_instance_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("lab_instances.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False
    )

    # Idempotency key to prevent duplicate launches
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), unique=True, index=True
    )

    # Job state
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False
    )  # pending | running | completed | failed | cancelled

    # Worker tracking
    worker_id: Mapped[str | None] = mapped_column(String(128))
    celery_task_id: Mapped[str | None] = mapped_column(String(128), index=True)
    compute_node_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("compute_nodes.id", ondelete="SET NULL")
    )

    # Retry tracking
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    # Configuration snapshot (frozen at creation time)
    config: Mapped[dict | None] = mapped_column(JSON)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Results
    error_message: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )


class ComputeNode(Base):
    """Registered compute host with capacity tracking."""

    __tablename__ = "compute_nodes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    hostname: Mapped[str] = mapped_column(String(256), nullable=False)
    provider_type: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # docker | libvirt | proxmox

    # Capacity
    total_cpu: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    total_memory_mb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_disk_gb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved_cpu: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    reserved_memory_mb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved_disk_gb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_instances: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    active_instances: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Connection details
    connection_uri: Mapped[str | None] = mapped_column(String(512))
    config: Mapped[dict | None] = mapped_column(JSON)

    # Health
    status: Mapped[str] = mapped_column(
        String(16), default="active", nullable=False
    )  # active | draining | offline | error
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health_check_result: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )


class ResourceReservation(Base):
    """Pre-allocated resources for a provisioning job."""

    __tablename__ = "resource_reservations"
    __table_args__ = (
        Index("ix_reservations_node_status", "compute_node_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("provisioning_jobs.id", ondelete="CASCADE"), nullable=False
    )
    compute_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("compute_nodes.id", ondelete="CASCADE"), nullable=False
    )

    # Reserved amounts
    cpu: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    memory_mb: Mapped[int] = mapped_column(Integer, default=512, nullable=False)
    disk_gb: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    status: Mapped[str] = mapped_column(
        String(16), default="reserved", nullable=False
    )  # reserved | consumed | released | expired

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
