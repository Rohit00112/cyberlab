"""Per-user hint reveals for progressive hints (PRD §22).

Each reveal is tracked so the penalty ``earned = base - hint_penalty * revealed``
can be applied at solve time. Reveals must be unlocked in order.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HintReveal(Base):
    __tablename__ = "hint_reveals"
    __table_args__ = (
        Index(
            "uq_hint_reveal",
            "user_id",
            "challenge_id",
            "hint_index",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("challenges.id", ondelete="CASCADE"), index=True, nullable=False
    )
    hint_index: Mapped[int] = mapped_column(Integer, nullable=False)
    revealed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )