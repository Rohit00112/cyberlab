"""Tests for lab state machine and valid transitions."""

import pytest

from app.core.states import (
    ACTIVE_STATES,
    CLEANUP_STATES,
    TERMINAL_STATES,
    InvalidTransitionError,
    LabState,
    can_transition,
    from_legacy,
    transition,
)


def test_valid_state_transitions():
    assert can_transition(LabState.QUEUED, LabState.PROVISIONING) is True
    assert can_transition(LabState.PROVISIONING, LabState.STARTING) is True
    assert can_transition(LabState.STARTING, LabState.RUNNING) is True
    assert can_transition(LabState.RUNNING, LabState.STOPPING) is True
    assert can_transition(LabState.STOPPING, LabState.STOPPED) is True
    assert can_transition(LabState.STOPPED, LabState.RESETTING) is True
    assert can_transition(LabState.RUNNING, LabState.EXPIRED) is True


def test_invalid_state_transitions():
    assert can_transition(LabState.QUEUED, LabState.RUNNING) is False
    assert can_transition(LabState.TERMINATED, LabState.RUNNING) is False

    with pytest.raises(InvalidTransitionError):
        transition(LabState.QUEUED, LabState.RUNNING)


def test_legacy_status_mapping():
    assert from_legacy("provisioning") == LabState.PROVISIONING
    assert from_legacy("running") == LabState.RUNNING
    assert from_legacy("stopped") == LabState.STOPPED
    assert from_legacy("error") == LabState.FAILED
    assert from_legacy("expired") == LabState.EXPIRED
    assert from_legacy("unknown_status") == LabState.FAILED


def test_state_sets():
    assert LabState.QUEUED in ACTIVE_STATES
    assert LabState.RUNNING in ACTIVE_STATES
    assert LabState.STOPPED not in ACTIVE_STATES
    assert LabState.TERMINATED in TERMINAL_STATES
    assert LabState.RUNNING in CLEANUP_STATES
