"""Learning paths and ordered steps (Phase 5, PRD §29)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LearningPath(Base):
    __tablename__ = "learning_paths"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(
        String(120), unique=True, index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_published: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class LearningPathStep(Base):
    __tablename__ = "learning_path_steps"
    __table_args__ = (
        Index(
            "uq_learning_path_challenge",
            "learning_path_id",
            "challenge_id",
            unique=True,
        ),
        Index("ix_learning_path_step_order", "learning_path_id", "step_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    learning_path_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("learning_paths.id", ondelete="CASCADE"),
        nullable=False,
    )
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("challenges.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
