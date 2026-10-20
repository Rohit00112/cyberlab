"""Strict Rust-core adapter response validation without a running service."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.core import rust_engine
from app.core.flags import hash_flag
from app.models.challenges import Challenge
from app.models.submissions import Submission
from app.models.users import User
from app.models.vpn_scoring import ScoreEvent
from app.services.submissions import submit_flag


@pytest.mark.asyncio
async def test_verify_accepts_explicit_boolean_only():
    with patch.object(rust_engine, "_post", new=AsyncMock(return_value={"correct": True})):
        assert await rust_engine.verify_flag("IIC{x}", "0" * 64)
    with patch.object(rust_engine, "_post", new=AsyncMock(return_value={"correct": 1})):
        with pytest.raises(HTTPException) as error:
            await rust_engine.verify_flag("IIC{x}", "0" * 64)
        assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_score_rejects_bad_response():
    with patch.object(rust_engine, "_post", new=AsyncMock(return_value={"points": -5})):
        with pytest.raises(HTTPException) as error:
            await rust_engine.calculate_score(
                base_points=500, solve_rank=1, mode="standard", penalty=0
            )
        assert error.value.status_code == 503


async def _seed_user_and_challenge(factory):
    async with factory() as db:
        user = User(
            keycloak_sub=f"rust-{uuid.uuid4().hex}",
            display_name="Rust Tester",
        )
        challenge = Challenge(
            slug=f"rust-test-{uuid.uuid4().hex}",
            title="Rust scoring test",
            description="Test an atomic score recording",
            category="Secure Coding",
            difficulty="beginner",
            points=150,
            hint_penalty=0,
            flag_hash=hash_flag("IIC{test}"),
            status="published",
        )
        db.add_all([user, challenge])
        await db.commit()
        return user.id, challenge.id


@pytest.mark.asyncio
async def test_rust_scoring_failure_does_not_record_a_solve(test_db, monkeypatch):
    user_id, challenge_id = await _seed_user_and_challenge(test_db)
    def settings():
        return SimpleNamespace(rust_core_url="http://127.0.0.1:8081")
    monkeypatch.setattr("app.services.submissions.get_settings", settings)
    monkeypatch.setattr("app.services.scoring.get_settings", settings)
    monkeypatch.setattr(
        "app.services.submissions.rust_verify_flag", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "app.services.scoring.calculate_score",
        AsyncMock(side_effect=HTTPException(status_code=503, detail="Rust unavailable")),
    )

    async with test_db() as db:
        challenge = await db.get(Challenge, challenge_id)
        with pytest.raises(HTTPException) as error:
            await submit_flag(
                db, user_id=user_id, challenge=challenge, flag="IIC{test}", can_edit=True
            )
        assert error.value.status_code == 503
        assert await db.scalar(select(func.count()).select_from(Submission)) == 0
        assert await db.scalar(select(func.count()).select_from(ScoreEvent)) == 0


@pytest.mark.asyncio
async def test_rust_score_recorded_atomically_with_submission(test_db, monkeypatch):
    user_id, challenge_id = await _seed_user_and_challenge(test_db)
    def settings():
        return SimpleNamespace(rust_core_url="http://127.0.0.1:8081")
    monkeypatch.setattr("app.services.submissions.get_settings", settings)
    monkeypatch.setattr("app.services.scoring.get_settings", settings)
    monkeypatch.setattr(
        "app.services.submissions.rust_verify_flag", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "app.services.scoring.calculate_score", AsyncMock(return_value=150)
    )

    async with test_db() as db:
        challenge = await db.get(Challenge, challenge_id)
        result = await submit_flag(
            db, user_id=user_id, challenge=challenge, flag="IIC{test}", can_edit=True
        )
        assert result.correct and result.points == 150
        submission = await db.scalar(select(Submission))
        event = await db.scalar(select(ScoreEvent))
        assert submission.earned_points == event.points == event.current_total == 150
        assert event.is_first_blood is True
