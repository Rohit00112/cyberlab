"""Durable reservations for operator-managed Proxmox staging VNets.

No user foreign key is intentional: deleting a user must never silently make
their former network available while a VM or route may still exist.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProxmoxSdnLease(Base):
    __tablename__ = "proxmox_sdn_leases"
    __table_args__ = (Index("ix_proxmox_sdn_leases_user_id", "user_id"),)

    vnet: Mapped[str] = mapped_column(String(8), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
