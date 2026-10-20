"""Rust catalog adapter and service integration with the existing ORM."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.core import rust_engine
from app.core.flags import hash_flag
from app.models.challenges import Challenge
from app.services import challenges


@pytest.mark.asyncio
async def test_rust_catalog_rejects_malformed_results(monkeypatch):
    monkeypatch.setattr(
        rust_engine, "_post", AsyncMock(return_value={"ids": ["invalid"], "total": 1})
    )
    with pytest.raises(HTTPException) as exc:
        await rust_engine.catalog_page(
            editor=False, category=None, difficulty=None, status=None, limit=10, offset=0
        )
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_rust_catalog_hydration_preserves_order_and_student_visibility(test_db, monkeypatch):
    async with test_db() as db:
        published = Challenge(
            slug=f"published-{uuid.uuid4().hex}", title="Published", description="d",
            category="Linux", difficulty="beginner", points=100,
            flag_hash=hash_flag("IIC{one}"), status="published",
        )
        private = Challenge(
            slug=f"private-{uuid.uuid4().hex}", title="Private", description="d",
            category="Linux", difficulty="beginner", points=200,
            flag_hash=hash_flag("IIC{two}"), status="draft",
        )
        db.add_all([published, private])
        await db.commit()
        monkeypatch.setattr(
            challenges, "get_settings",
            lambda: SimpleNamespace(rust_core_url="http://security-core:8081"),
        )
        monkeypatch.setattr(challenges, "can_edit", AsyncMock(return_value=False))
        monkeypatch.setattr(
            challenges, "catalog_page",
            AsyncMock(return_value=([str(private.id), str(published.id)], 2)),
        )
        results, total = await challenges.list_challenges(db, ["student"])
        assert [result.id for result in results] == [published.id]
        assert total == 2


@pytest.mark.asyncio
async def test_catalog_core_failure_propagates(test_db, monkeypatch):
    monkeypatch.setattr(
        challenges, "get_settings",
        lambda: SimpleNamespace(rust_core_url="http://security-core:8081"),
    )
    monkeypatch.setattr(challenges, "can_edit", AsyncMock(return_value=False))
    monkeypatch.setattr(
        challenges, "catalog_page",
        AsyncMock(side_effect=HTTPException(status_code=503, detail="Core unavailable")),
    )
    async with test_db() as db:
        with pytest.raises(HTTPException) as exc:
            await challenges.list_challenges(db, ["student"])
        assert exc.value.status_code == 503
