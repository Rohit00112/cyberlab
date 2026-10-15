"""VPN peer and scoring event models."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VPNPeer(Base):
    """WireGuard VPN peer configuration for a user or team."""

    __tablename__ = "vpn_peers"
    __table_args__ = (
        Index("ix_vpn_peers_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("teams.id", ondelete="SET NULL")
    )

    # WireGuard keys (public key only — private key never stored server-side)
    public_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    preshared_key_hash: Mapped[str | None] = mapped_column(String(128))

    # Assigned addressing
    assigned_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    allowed_ips: Mapped[str] = mapped_column(String(512), nullable=False)

    # Network scope — which lab networks this peer can reach
    lab_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("lab_instances.id", ondelete="SET NULL")
    )

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(16), default="active", nullable=False
    )  # active | revoked | expired
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Config download tracking
    config_downloaded: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_handshake: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )


class ScoreEvent(Base):
    """Granular scoring record for dynamic scoring and competitions.

    Decoupled from ``Submission`` so scoring can be recalculated, have
    bonuses applied (first-blood), or be adjusted by competition rules.
    """

    __tablename__ = "score_events"
    __table_args__ = (
        Index("ix_score_events_user_challenge", "user_id", "challenge_id"),
        Index("ix_score_events_competition", "competition_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False
    )
    competition_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("competitions.id", ondelete="SET NULL")
    )
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("submissions.id", ondelete="SET NULL")
    )

    # Scoring details
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # solve | first_blood | hint_penalty | bonus | adjustment
    base_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    modifier: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    final_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Dynamic scoring context
    solve_count_at_time: Mapped[int | None] = mapped_column(Integer)
    decay_factor: Mapped[float | None] = mapped_column(Float)

    reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
