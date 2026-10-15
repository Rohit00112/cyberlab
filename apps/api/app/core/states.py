"""Lab instance state machine with validated transitions.

Every lab instance follows a well-defined lifecycle. Transitions are
validated at the service layer — callers must go through ``transition()``
to change state, which guarantees only valid arcs are taken.
"""

from __future__ import annotations

from enum import StrEnum


class LabState(StrEnum):
    """All possible lab instance states."""

    QUEUED = "queued"
    PROVISIONING = "provisioning"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    RESETTING = "resetting"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    FAILED = "failed"
    EXPIRED = "expired"


# ---------- valid transitions ----------

_TRANSITIONS: dict[LabState, set[LabState]] = {
    LabState.QUEUED: {LabState.PROVISIONING, LabState.FAILED, LabState.TERMINATED},
    LabState.PROVISIONING: {LabState.STARTING, LabState.FAILED, LabState.TERMINATED},
    LabState.STARTING: {LabState.RUNNING, LabState.FAILED, LabState.TERMINATED},
    LabState.RUNNING: {
        LabState.STOPPING,
        LabState.RESETTING,
        LabState.TERMINATING,
        LabState.EXPIRED,
        LabState.FAILED,
    },
    LabState.STOPPING: {LabState.STOPPED, LabState.FAILED},
    LabState.STOPPED: {
        LabState.STARTING,
        LabState.RESETTING,
        LabState.TERMINATING,
        LabState.TERMINATED,
    },
    LabState.RESETTING: {
        LabState.PROVISIONING,
        LabState.FAILED,
        LabState.TERMINATED,
    },
    LabState.TERMINATING: {LabState.TERMINATED, LabState.FAILED},
    LabState.TERMINATED: set(),  # terminal
    LabState.FAILED: {LabState.QUEUED, LabState.TERMINATING, LabState.TERMINATED},
    LabState.EXPIRED: {LabState.TERMINATING, LabState.TERMINATED, LabState.RESETTING},
}

#: States that count toward the user's active-instance quota.
ACTIVE_STATES: frozenset[LabState] = frozenset(
    {
        LabState.QUEUED,
        LabState.PROVISIONING,
        LabState.STARTING,
        LabState.RUNNING,
    }
)

#: Terminal states — no further transitions possible.
TERMINAL_STATES: frozenset[LabState] = frozenset(
    {
        LabState.TERMINATED,
    }
)

#: States that need infrastructure cleanup.
CLEANUP_STATES: frozenset[LabState] = frozenset(
    {
        LabState.RUNNING,
        LabState.STOPPING,
        LabState.STOPPED,
        LabState.FAILED,
        LabState.EXPIRED,
    }
)


class InvalidTransitionError(ValueError):
    """Raised when a state transition is not allowed."""

    def __init__(self, current: LabState, target: LabState) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Invalid state transition: {current} → {target}")


def can_transition(current: LabState | str, target: LabState | str) -> bool:
    """Check whether a transition from ``current`` to ``target`` is valid."""
    current = LabState(current)
    target = LabState(target)
    return target in _TRANSITIONS.get(current, set())


def transition(current: LabState | str, target: LabState | str) -> LabState:
    """Validate and return the target state, or raise ``InvalidTransitionError``."""
    current = LabState(current)
    target = LabState(target)
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)
    return target


# Legacy compat — map old string statuses to LabState values.
_LEGACY_MAP: dict[str, LabState] = {
    "provisioning": LabState.PROVISIONING,
    "running": LabState.RUNNING,
    "stopped": LabState.STOPPED,
    "error": LabState.FAILED,
    "expired": LabState.EXPIRED,
}


def from_legacy(status: str) -> LabState:
    """Convert an existing database status string to a ``LabState``."""
    try:
        return LabState(status)
    except ValueError:
        return _LEGACY_MAP.get(status, LabState.FAILED)
