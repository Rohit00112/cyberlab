"""Machine template models for the machine builder system.

A MachineTemplate describes a reusable vulnerable machine definition.
MachineTemplateVersion captures immutable, versioned snapshots that are
built, validated, and published. Challenges reference a specific version.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MachineTemplate(Base):
    """Reusable machine definition (admin-managed)."""

    __tablename__ = "machine_templates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False, default="intermediate")

    # Infrastructure specification
    os_type: Mapped[str] = mapped_column(String(32), nullable=False, default="linux")
    architecture: Mapped[str] = mapped_column(String(16), nullable=False, default="x86_64")
    base_image: Mapped[str] = mapped_column(String(512), nullable=False)
    services: Mapped[list | None] = mapped_column(JSON)  # list of service definitions
    challenge_modules: Mapped[list | None] = mapped_column(JSON)  # vulnerability modules
    resource_spec: Mapped[dict | None] = mapped_column(JSON)  # cpu, memory, disk

    # Network and exposure
    network_policy: Mapped[dict | None] = mapped_column(JSON)  # ports, protocols, isolation
    exposure_policy: Mapped[str] = mapped_column(
        String(16), default="vpn_only", nullable=False
    )  # vpn_only | internal | restricted_public

    # Flags and hints
    flag_definitions: Mapped[list | None] = mapped_column(JSON)  # flag placement configs
    hint_config: Mapped[list | None] = mapped_column(JSON)

    # Lifecycle
    max_lease_minutes: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)

    # Metadata
    tags: Mapped[list | None] = mapped_column(JSON)
    prerequisites: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(16), default="draft", nullable=False
    )  # draft | review | approved | published | archived

    author_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )


class MachineTemplateVersion(Base):
    """Immutable, versioned snapshot of a machine template."""

    __tablename__ = "machine_template_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("machine_templates.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Frozen configuration snapshot
    config_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Build artifacts
    image_ref: Mapped[str | None] = mapped_column(String(512))  # built image reference
    image_hash: Mapped[str | None] = mapped_column(String(128))  # SHA-256 of the image
    build_log: Mapped[str | None] = mapped_column(Text)
    artifact_manifest: Mapped[dict | None] = mapped_column(JSON)

    # Status
    status: Mapped[str] = mapped_column(
        String(16), default="building", nullable=False
    )  # building | validating | validated | failed | published | deprecated

    # Validation
    validation_result: Mapped[dict | None] = mapped_column(JSON)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
