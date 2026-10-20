"""Async lab transition guard backed by Rust when the security core is enabled."""

from app.core.config import get_settings
from app.core.rust_engine import can_transition_lab
from app.core.states import InvalidTransitionError, LabState, from_legacy, transition


async def transition_lab(current: LabState | str, target: LabState | str) -> LabState:
    source = from_legacy(str(current))
    destination = LabState(target)
    if get_settings().rust_core_url:
        if not await can_transition_lab(source.value, destination.value):
            raise InvalidTransitionError(source, destination)
        return destination
    return transition(source, destination)
