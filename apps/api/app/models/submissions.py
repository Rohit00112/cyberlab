"""Submission model. One row per flag attempt; correct solves are unique per (user, challenge).

Scoring (PRD §21 MVP): Final Points = Base Challenge Points - Hint Penalties.
Hints are unrevealed for MVP, so a solve earns the full base points exactly once.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        Index(
            "uq_submissions_correct",
            "challenge_id",
            "user_id",
            unique=True,
            postgresql_where=text("is_correct"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("challenges.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    earned_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )