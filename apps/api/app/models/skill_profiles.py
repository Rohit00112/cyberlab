"""Explicit user skill competency profiles (Phase 5, PRD §28)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserSkillProfile(Base):
    __tablename__ = "user_skill_profiles"
    __table_args__ = (
        Index("uq_user_skill_profile", "user_id", "skill_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    competency_level: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )
