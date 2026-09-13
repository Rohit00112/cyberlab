"""Challenge model (see PRD §15/§16)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    skills: Mapped[list[str] | None] = mapped_column(JSON)
    prerequisites: Mapped[list[str] | None] = mapped_column(JSON)
    hints: Mapped[list[str] | None] = mapped_column(JSON)
    hint_penalty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    flag_hash: Mapped[str | None] = mapped_column(String(64))
    flag_format: Mapped[str | None] = mapped_column(String(120))
    environment_type: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow
    )

    @property
    def is_published(self) -> bool:
        return self.status == "published"