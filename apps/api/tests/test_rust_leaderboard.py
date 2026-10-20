"""Leaderboard contract and fail-closed integration tests."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.core import rust_engine
from app.services import submissions


@pytest.mark.asyncio
async def test_rust_leaderboard_response_is_validated(monkeypatch):
    monkeypatch.setattr(
        rust_engine, "_post",
        AsyncMock(return_value=[{
            "rank": 1, "user_id": str(uuid.uuid4()), "display_name": "Student",
            "points": 200, "solved_count": 2,
        }]),
    )
    rows = await rust_engine.global_leaderboard(50)
    assert len(rows) == 1 and rows[0]["points"] == 200


@pytest.mark.asyncio
async def test_rust_leaderboard_bad_rank_fails_closed(monkeypatch):
    monkeypatch.setattr(
        rust_engine, "_post",
        AsyncMock(return_value=[{
            "rank": 0, "user_id": str(uuid.uuid4()), "display_name": "Student",
            "points": 200, "solved_count": 2,
        }]),
    )
    with pytest.raises(HTTPException) as exc:
        await rust_engine.global_leaderboard(50)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_rust_leaderboard_is_authoritative(monkeypatch):
    monkeypatch.setattr(
        submissions, "get_settings",
        lambda: SimpleNamespace(rust_core_url="http://security-core:8081"),
    )
    monkeypatch.setattr(
        rust_engine, "_post",
        AsyncMock(side_effect=HTTPException(status_code=503, detail="Core unavailable")),
    )
    with pytest.raises(HTTPException) as exc:
        await submissions.leaderboard(None)
    assert exc.value.status_code == 503
