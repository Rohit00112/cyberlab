"""Lab instance model. One row per provisioned per-user lab (Phase 2).

Labs are isolated per user (dedicated bridge network) and only reachable
through the CyberLab API — never through a direct infrastructure handle.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LabInstance(Base):
    __tablename__ = "lab_instances"
    __table_args__ = (
        Index("ix_lab_instances_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default="provisioning", nullable=False
    )
    container_id: Mapped[str | None] = mapped_column(String(128))
    container_name: Mapped[str | None] = mapped_column(String(128))
    network_name: Mapped[str | None] = mapped_column(String(128))
    connection_hint: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )