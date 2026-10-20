"""Competition state decisions; delegate to Rust when the internal core is enabled."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.rust_engine import competition_transition

TRANSITIONS = {
    "start_registration": ("draft", "registration"),
    "schedule": ("registration", "scheduled"),
    "start": ("scheduled", "live"),
    "finish": ("live", "finished"),
    "archive": ("finished", "archived"),
}


def _timestamp(value: datetime | None) -> int | None:
    if value is None:
        return None
    return int(value.replace(tzinfo=UTC).timestamp() * 1_000)


async def decide_competition_transition(
    current: str,
    action: str,
    *,
    start_at: datetime | None,
    end_at: datetime | None,
    now: datetime,
) -> tuple[str | None, str | None]:
    """Return (next_status, error_code) for organizer or auto transition.

    A null next_status is permitted only for the auto scheduler.
    """
    if get_settings().rust_core_url:
        return await competition_transition(
            current,
            action,
            start_at=_timestamp(start_at),
            end_at=_timestamp(end_at),
            now=_timestamp(now),
        )

    if action == "auto":
        if current == "scheduled" and start_at and now >= start_at.replace(tzinfo=UTC):
            return "live", None
        if current == "live" and end_at and now >= end_at.replace(tzinfo=UTC):
            return "finished", None
        return None, None

    allowed = TRANSITIONS.get(action)
    if allowed is None:
        return None, "unknown_action"
    from_status, to_status = allowed
    if current != from_status:
        return None, "invalid_transition"
    if action == "schedule" and not (start_at and end_at):
        return None, "missing_schedule"
    if action == "start" and start_at and start_at.replace(tzinfo=UTC) > now + timedelta(minutes=5):
        return None, "too_early"
    return to_status, None
