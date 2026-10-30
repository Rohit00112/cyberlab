"""Competition policy and database integration tests for Rust migration."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.core import competition_transitions, rust_engine
from app.models.challenges import Challenge
from app.models.competitions import Competition, CompetitionParticipant
from app.models.users import User
from app.schemas.competition import CompetitionUpdate
from app.services import competitions
from app.services.competitions import auto_transition_competitions, transition


@pytest.mark.parametrize(
    ("current", "action", "expected", "error"),
    [
        ("draft", "start_registration", "registration", None),
        ("registration", "schedule", "scheduled", None),
        ("scheduled", "start", "live", None),
        ("live", "finish", "finished", None),
        ("finished", "archive", "archived", None),
        ("draft", "start", None, "invalid_transition"),
        ("draft", "invalid", None, "unknown_action"),
    ],
)
@pytest.mark.asyncio
async def test_fallback_organizer_actions(monkeypatch, current, action, expected, error):
    monkeypatch.setattr(
        competition_transitions,
        "get_settings",
        lambda: SimpleNamespace(rust_core_url=""),
    )
    now = datetime.now(UTC)
    result = await competition_transitions.decide_competition_transition(
        current,
        action,
        start_at=now - timedelta(minutes=10),
        end_at=now + timedelta(minutes=10),
        now=now,
    )
    assert result == (expected, error)


@pytest.mark.asyncio
async def test_rust_decision_is_authoritative_without_python_fallback(monkeypatch):
    monkeypatch.setattr(
        competition_transitions,
        "get_settings",
        lambda: SimpleNamespace(rust_core_url="http://security-core:8081"),
    )
    endpoint = AsyncMock(return_value=(None, "invalid_transition"))
    monkeypatch.setattr(competition_transitions, "competition_transition", endpoint)
    decision = await competition_transitions.decide_competition_transition(
        "draft",
        "start_registration",
        start_at=None,
        end_at=None,
        now=datetime.now(UTC),
    )
    assert decision == (None, "invalid_transition")
    endpoint.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_rust_response_fails_closed(monkeypatch):
    monkeypatch.setattr(
        rust_engine,
        "_post",
        AsyncMock(return_value={"next_status": "administrator", "error_code": None}),
    )
    with pytest.raises(HTTPException) as exc:
        await rust_engine.competition_transition(
            "draft", "start_registration", start_at=None, end_at=None, now=0
        )
    assert exc.value.status_code == 503


async def _seed_competition(db, status="draft", *, start_at=None, end_at=None):
    user = User(keycloak_sub=f"comp-user-{uuid.uuid4().hex}", display_name="Organizer")
    db.add(user)
    await db.flush()
    comp = Competition(
        slug=f"rust-comp-{uuid.uuid4().hex}",
        title="Rust-backed competition",
        created_by=user.id,
        status=status,
        start_at=start_at,
        end_at=end_at,
    )
    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return comp, user


@pytest.mark.asyncio
async def test_manual_transition_persists_and_rejects_invalid_actions(test_db):
    async with test_db() as db:
        competition, user = await _seed_competition(db)
        result = await transition(db, competition, "start_registration", user)
        assert result.status == "registration"
        with pytest.raises(HTTPException) as exc:
            await transition(db, competition, "start", user)
        assert exc.value.status_code == 409
        await db.refresh(competition)
        assert competition.status == "registration"


@pytest.mark.asyncio
async def test_scheduler_transitions_persist_without_changing_future_events(test_db):
    now = datetime.now(UTC)
    async with test_db() as db:
        scheduled, _ = await _seed_competition(
            db, "scheduled",
            start_at=now - timedelta(minutes=15),
            end_at=now + timedelta(minutes=15),
        )
        finished, _ = await _seed_competition(
            db, "live", end_at=now - timedelta(minutes=1)
        )
        future, _ = await _seed_competition(
            db, "scheduled", start_at=now + timedelta(hours=1)
        )
        assert await auto_transition_competitions(db) == 2
        await db.refresh(scheduled)
        await db.refresh(finished)
        await db.refresh(future)
        assert scheduled.status == "live"
        assert finished.status == "finished"
        assert future.status == "scheduled"


@pytest.mark.asyncio
async def test_core_unavailable_does_not_change_competition(test_db, monkeypatch):
    async with test_db() as db:
        competition, user = await _seed_competition(db)
        monkeypatch.setattr(
            competition_transitions,
            "get_settings",
            lambda: SimpleNamespace(rust_core_url="http://security-core:8081"),
        )
        monkeypatch.setattr(
            competition_transitions,
            "competition_transition",
            AsyncMock(side_effect=HTTPException(status_code=503, detail="Rust unavailable")),
        )
        with pytest.raises(HTTPException) as exc:
            await transition(db, competition, "start_registration", user)
        assert exc.value.status_code == 503
        await db.refresh(competition)
        assert competition.status == "draft"


@pytest.mark.asyncio
async def test_competition_edit_python_fallback_remains_available(test_db, monkeypatch):
    monkeypatch.setattr(
        competitions, "get_settings", lambda: SimpleNamespace(rust_core_url="")
    )
    async with test_db() as db:
        competition, user = await _seed_competition(db)
        response = await competitions.update_competition(
            db, competition, CompetitionUpdate(title="Fallback edited"), user
        )
        assert response.title == "Fallback edited"
        await db.refresh(competition)
        assert competition.title == "Fallback edited"


@pytest.mark.parametrize(
    ("outcome", "http_status"),
    [("not_found", 404), ("locked", 409), ("unexpected", 503)],
)
@pytest.mark.asyncio
async def test_rust_competition_edit_outcomes_fail_closed(monkeypatch, outcome, http_status):
    monkeypatch.setattr(rust_engine, "_post", AsyncMock(return_value={"outcome": outcome}))
    with pytest.raises(HTTPException) as exc:
        await rust_engine.edit_competition_in_rust(
            str(uuid.uuid4()), str(uuid.uuid4()), ["faculty"], None, {"title": "Edit"}
        )
    assert exc.value.status_code == http_status


@pytest.mark.asyncio
async def test_competition_challenge_links_python_fallback(test_db, monkeypatch):
    monkeypatch.setattr(
        competitions, "get_settings", lambda: SimpleNamespace(rust_core_url="")
    )
    async with test_db() as db:
        competition, user = await _seed_competition(db)
        challenge = Challenge(
            slug=f"fallback-link-{uuid.uuid4().hex[:10]}", title="Fallback link",
            description="Test", category="Linux", difficulty="beginner",
            points=50, status="published",
        )
        db.add(challenge)
        await db.commit()
        linked = await competitions.add_challenge(db, competition, challenge.id, None, user)
        assert linked.challenge_count == 1
        removed = await competitions.remove_challenge(db, competition, challenge.id, user)
        assert removed.challenge_count == 0


@pytest.mark.parametrize(
    ("action", "outcome", "http_status"),
    [
        ("add", "challenge_not_found", 404),
        ("add", "duplicate", 409),
        ("remove", "locked", 409),
        ("remove", "unexpected", 503),
    ],
)
@pytest.mark.asyncio
async def test_rust_competition_link_outcomes_fail_closed(
    monkeypatch, action, outcome, http_status
):
    monkeypatch.setattr(rust_engine, "_post", AsyncMock(return_value={"outcome": outcome}))
    with pytest.raises(HTTPException) as exc:
        await rust_engine.link_competition_challenge_in_rust(
            action, str(uuid.uuid4()), str(uuid.uuid4()),
            str(uuid.uuid4()), ["faculty"], None,
        )
    assert exc.value.status_code == http_status


@pytest.mark.asyncio
async def test_competition_registration_python_fallback(test_db, monkeypatch):
    monkeypatch.setattr(
        competitions, "get_settings", lambda: SimpleNamespace(rust_core_url="")
    )
    async with test_db() as db:
        competition, user = await _seed_competition(db, "registration")
        registered = await competitions.register(db, competition, user)
        assert registered.participant_count == 1
        with pytest.raises(HTTPException) as duplicate:
            await competitions.register(db, competition, user)
        assert duplicate.value.status_code == 409
        unregistered = await competitions.unregister(db, competition, user)
        assert unregistered.participant_count == 0
        with pytest.raises(HTTPException) as missing:
            await competitions.unregister(db, competition, user)
        assert missing.value.status_code == 409


@pytest.mark.parametrize(
    ("action", "response", "http_status"),
    [
        ("register", {"outcome": "closed", "current_status": "draft"}, 409),
        ("register", {"outcome": "closed", "current_status": "untrusted"}, 503),
        ("register", {"outcome": "already_registered"}, 409),
        ("unregister", {"outcome": "not_registered"}, 409),
        ("unregister", {"outcome": "unknown"}, 503),
    ],
)
@pytest.mark.asyncio
async def test_rust_registration_outcomes_are_validated(
    monkeypatch, action, response, http_status
):
    monkeypatch.setattr(rust_engine, "_post", AsyncMock(return_value=response))
    with pytest.raises(HTTPException) as exc:
        await rust_engine.change_competition_registration_in_rust(
            action, str(uuid.uuid4()), str(uuid.uuid4()), ["student"], None
        )
    assert exc.value.status_code == http_status


@pytest.mark.asyncio
async def test_competition_teams_python_fallback(test_db, monkeypatch):
    monkeypatch.setattr(
        competitions, "get_settings", lambda: SimpleNamespace(rust_core_url="")
    )
    async with test_db() as db:
        competition, captain = await _seed_competition(db, "registration")
        competition.allow_teams = True
        teammate = User(
            keycloak_sub=f"team-fallback-{uuid.uuid4().hex}", display_name="Teammate",
        )
        db.add(teammate)
        await db.flush()
        db.add_all([
            CompetitionParticipant(competition_id=competition.id, user_id=captain.id),
            CompetitionParticipant(competition_id=competition.id, user_id=teammate.id),
        ])
        await db.commit()
        created = await competitions.create_team(db, competition, "Legacy team", captain)
        assert created.team_count == 1
        assert created.me.team.role == "captain"
        with pytest.raises(HTTPException) as duplicate:
            await competitions.create_team(db, competition, "Second captain", captain)
        assert duplicate.value.status_code == 409
        joined = await competitions.join_team(
            db, competition, created.me.team.id, teammate
        )
        assert joined.me.team.role == "member"
        assert joined.me.team.member_count == 2


@pytest.mark.parametrize(
    ("action", "response", "http_status"),
    [
        ("create", {"outcome": "not_registered"}, 409),
        ("join", {"outcome": "team_not_found"}, 404),
        ("join", {"outcome": "already_on_team"}, 409),
        ("join", {"outcome": "full", "max_team_size": 2}, 409),
        ("join", {"outcome": "full", "max_team_size": "invalid"}, 503),
        ("create", {"outcome": "closed", "current_status": "unknown"}, 503),
        ("create", {"outcome": "unexpected"}, 503),
    ],
)
@pytest.mark.asyncio
async def test_rust_team_outcomes_are_validated(
    monkeypatch, action, response, http_status
):
    monkeypatch.setattr(rust_engine, "_post", AsyncMock(return_value=response))
    with pytest.raises(HTTPException) as exc:
        await rust_engine.change_competition_team_in_rust(
            action, str(uuid.uuid4()), str(uuid.uuid4()), ["student"], None,
            name="Team" if action == "create" else None,
            team_id=str(uuid.uuid4()) if action == "join" else None,
        )
    assert exc.value.status_code == http_status


@pytest.mark.asyncio
async def test_competition_freeze_python_fallback(test_db, monkeypatch):
    monkeypatch.setattr(
        competitions, "get_settings", lambda: SimpleNamespace(rust_core_url="")
    )
    async with test_db() as db:
        competition, user = await _seed_competition(db, "finished")
        frozen = await competitions.freeze(db, competition, user, frozen=True)
        assert frozen.freeze_leaderboard is True
        assert frozen.frozen_at is not None
        unfrozen = await competitions.freeze(db, competition, user, frozen=False)
        assert unfrozen.freeze_leaderboard is False
        assert unfrozen.frozen_at is None


@pytest.mark.parametrize(
    ("result", "http_status"),
    [
        ({"outcome": "not_found"}, 404),
        ({"outcome": "unexpected"}, 503),
        ({"outcome": None}, 503),
    ],
)
@pytest.mark.asyncio
async def test_rust_competition_freeze_outcomes_fail_closed(
    monkeypatch, result, http_status
):
    monkeypatch.setattr(rust_engine, "_post", AsyncMock(return_value=result))
    with pytest.raises(HTTPException) as exc:
        await rust_engine.set_competition_frozen_in_rust(
            str(uuid.uuid4()), str(uuid.uuid4()), ["faculty"], None, True
        )
    assert exc.value.status_code == http_status


@pytest.mark.parametrize(
    ("action", "response", "http_status"),
    [
        ("start", {"outcome": "too_early"}, 409),
        ("schedule", {"outcome": "missing_schedule"}, 400),
        ("finish", {"outcome": "not_found"}, 404),
        ("start", {"outcome": "invalid_transition", "current_status": "draft"}, 409),
        ("start", {"outcome": "invalid_transition", "current_status": []}, 503),
        ("finish", {
            "outcome": "updated", "current_status": "live", "next_status": "admin",
        }, 503),
        ("archive", {"outcome": "unexpected"}, 503),
    ],
)
@pytest.mark.asyncio
async def test_rust_persistent_transition_outcomes_are_validated(
    monkeypatch, action, response, http_status
):
    monkeypatch.setattr(rust_engine, "_post", AsyncMock(return_value=response))
    with pytest.raises(HTTPException) as exc:
        await rust_engine.persist_competition_transition_in_rust(
            str(uuid.uuid4()), action, str(uuid.uuid4()), ["faculty"], None
        )
    assert exc.value.status_code == http_status
