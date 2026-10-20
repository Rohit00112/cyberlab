"""VPN peer and scoring event models."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VPNPeer(Base):
    """WireGuard VPN peer (matches the existing Alembic schema)."""

    __tablename__ = "vpn_peers"
    __table_args__ = (
        Index("ix_vpn_peers_user_id", "user_id"),
        Index("ix_vpn_peers_public_key", "public_key", unique=True),
        Index("ix_vpn_peers_allocated_ip", "allocated_ip", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # WireGuard keys (public key only — private key never stored server-side)
    public_key: Mapped[str] = mapped_column(String(64), nullable=False)
    preshared_key_hash: Mapped[str | None] = mapped_column(String(128))

    # Assigned addressing
    allocated_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    allowed_subnets: Mapped[list[str] | None] = mapped_column(JSON)

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handshake_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tx_bytes: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0"), nullable=False
    )
    rx_bytes: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class ScoreEvent(Base):
    """Granular scoring record for dynamic scoring and competitions.

    Decoupled from ``Submission`` so scoring can be recalculated, have
    bonuses applied (first-blood), or be adjusted by competition rules.
    """

    __tablename__ = "score_events"
    __table_args__ = (
        Index("ix_score_events_user_id", "user_id"),
        Index("ix_score_events_competition_id", "competition_id"),
        Index("ix_score_events_recorded_at", "recorded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    challenge_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("challenges.id", ondelete="SET NULL")
    )
    competition_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("competitions.id", ondelete="SET NULL")
    )
    # Scoring details
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # solve | first_blood | hint_penalty | bonus | adjustment
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    current_total: Mapped[int] = mapped_column(Integer, nullable=False)
    is_first_blood: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    is_frozen: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
