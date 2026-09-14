"""Tests for the Phase 6 research platform (§70-§72).

Covers pseudonymization guarantees, dataset build/download/expiry/delete,
metrics + graph aggregation, recommendation impression logging (deduped), the
experiment registry, and permission gating (students cannot reach /research/**).
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.api.deps import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.models import (
    Challenge,
    ChallengeSkill,
    RecommendationLog,
    Skill,
    Submission,
    User,
)
from app.models.hint_reveals import HintReveal
from app.models.research import ResearchDataset
from app.schemas.research import DatasetCreate
from app.services import research as research_service
from app.services.recommendations import get_recommendations


def _researcher() -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub="researcher-sub-test",
        roles=["student", "researcher"],
        permissions=[
            "challenge.view",
            "skill.view",
            "analytics.view",
            "analytics.research",
            "user.manage",
        ],
    )


@pytest.fixture
async def researcher_client(test_db, tmp_path, monkeypatch):
    user = _researcher()
    async with test_db() as db:
        if await db.get(User, user.id) is None:
            db.add(
                User(
                    id=user.id,
                    keycloak_sub=user.keycloak_sub,
                    email="researcher@cyberlab.test",
                    display_name="Researcher",
                )
            )
            await db.commit()
    monkeypatch.setattr(research_service, "RESEARCH_DIR_OVERRIDE", tmp_path)

    async def _db() -> AsyncIterator:
        async with test_db() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    yield client, user
    app.dependency_overrides.clear()


async def _seed_solved_challenge(
    test_db, *, user_id: uuid.UUID | None = None
) -> tuple[uuid.UUID, uuid.UUID]:
    """Creates a published challenge + skill link and a correct solve."""
    async with test_db() as db:
        skill = Skill(slug=f"sk_{uuid.uuid4().hex[:6]}", name="Research Skill", is_active=True)
        challenge = Challenge(
            slug=f"rc_{uuid.uuid4().hex[:6]}",
            title="Research Challenge",
            description="desc",
            category="Linux",
            difficulty="beginner",
            points=50,
            status="published",
        )
        db.add_all([skill, challenge])
        await db.flush()
        db.add(ChallengeSkill(challenge_id=challenge.id, skill_id=skill.id))
        uid = user_id or uuid.uuid4()
        if user_id is None:
            db.add(
                User(
                    id=uid,
                    keycloak_sub=f"rc_user_{uuid.uuid4().hex[:6]}",
                    email="rc@test.com",
                    display_name="RC",
                )
            )
        await db.flush()
        db.add(
            Submission(user_id=uid, challenge_id=challenge.id, is_correct=True, earned_points=50)
        )
        await db.commit()
        return challenge.id, skill.id


# --- Pseudonymization ------------------------------------------------------- #

@pytest.mark.asyncio
async def test_participant_id_deterministic_and_irreversible():
    from app.core.pseudonym import participant_id

    a = participant_id("sub-123")
    b = participant_id("sub-123")
    assert a == b
    assert a != participant_id("sub-456")
    assert len(a) == 16
    assert all(ch in "0123456789abcdef" for ch in a)
    assert "sub-123" not in a


# --- Datasets --------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_dataset_build_no_pii(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(research_service, "RESEARCH_DIR_OVERRIDE", tmp_path)
    async with test_db() as db:
        user = User(
            id=uuid.uuid4(),
            keycloak_sub="pii-user-sub",
            email="secret@cyberlab.test",
            display_name="Secret Name",
            roles=["student"],
        )
        db.add(user)
        challenge = Challenge(
            slug="pii_c",
            title="PII",
            description="d",
            category="Linux",
            difficulty="beginner",
            points=10,
            status="published",
        )
        db.add(challenge)
        await db.flush()
        db.add(
            Submission(
                user_id=user.id, challenge_id=challenge.id, is_correct=True, earned_points=10
            )
        )
        await db.commit()

        dataset = await research_service.build_dataset(
            db, DatasetCreate(name="PII export", kind="submissions"), created_by=user.id
        )
        assert dataset.row_count == 1
        assert dataset.pseudonymized is True
        assert dataset.expires_at is not None
        assert dataset.expires_at > datetime.now(UTC) + timedelta(days=29)

        path = research_service.dataset_artifact_path(dataset)
        rows = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        joined = json.dumps(rows)
        assert "secret@cyberlab.test" not in joined
        assert "Secret Name" not in joined
        assert "pii-user-sub" not in joined
        assert "user_id" not in rows[0]
        assert rows[0]["participant_id"]


@pytest.mark.asyncio
async def test_dataset_download_and_expiry(researcher_client, test_db, tmp_path, monkeypatch):
    from app.core.pseudonym import participant_id

    monkeypatch.setattr(research_service, "RESEARCH_DIR_OVERRIDE", tmp_path)
    client, researcher = researcher_client
    await _seed_solved_challenge(test_db, user_id=researcher.id)

    resp = await client.post(
        "/api/v1/research/datasets",
        json={"name": "evals", "kind": "submissions", "expires_in_days": 7},
    )
    assert resp.status_code == 201, resp.text
    dataset = resp.json()
    assert dataset["row_count"] == 1

    listed = await client.get("/api/v1/research/datasets")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    downloaded = await client.get(f"/api/v1/research/datasets/{dataset['id']}/download?format=json")
    assert downloaded.status_code == 200
    body = downloaded.content.decode("utf-8")
    assert participant_id("researcher-sub-test") in body
    assert "researcher@cyberlab.test" not in body

    async with test_db() as db:
        stored = await db.get(ResearchDataset, uuid.UUID(dataset["id"]))
        stored.expires_at = datetime.now(UTC) - timedelta(days=1)
        await db.commit()
    gone = await client.get(f"/api/v1/research/datasets/{dataset['id']}/download")
    assert gone.status_code == 410

    deleted = await client.delete(f"/api/v1/research/datasets/{dataset['id']}")
    assert deleted.status_code == 204
    assert not (tmp_path / f"{dataset['id']}.csv").exists()


@pytest.mark.asyncio
async def test_metrics_shape(researcher_client, test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(research_service, "RESEARCH_DIR_OVERRIDE", tmp_path)
    client, researcher = researcher_client
    challenge_id, _ = await _seed_solved_challenge(test_db, user_id=researcher.id)

    async with test_db() as db:
        db.add(HintReveal(user_id=researcher.id, challenge_id=challenge_id, hint_index=0))
        await db.commit()

    resp = await client.get("/api/v1/research/metrics")
    assert resp.status_code == 200, resp.text
    metrics = resp.json()
    assert metrics["learning"]["assessed_users"] == 1
    assert metrics["learning"]["completion_rate"] == 1.0
    assert metrics["engagement"]["challenges_attempted"] == 1
    assert metrics["engagement"]["hints_used"] == 1
    assert len(metrics["challenge_quality"]) >= 1
    assert metrics["recommendations"]["served"] == 0


@pytest.mark.asyncio
async def test_graph_contains_challenge_skill_category(
    researcher_client, test_db, tmp_path, monkeypatch
):
    monkeypatch.setattr(research_service, "RESEARCH_DIR_OVERRIDE", tmp_path)
    client, _ = researcher_client
    challenge_id, skill_id = await _seed_solved_challenge(test_db)

    resp = await client.get("/api/v1/research/graph")
    assert resp.status_code == 200, resp.text
    graph = resp.json()
    ids = {node["id"] for node in graph["nodes"]}
    assert f"challenge:{challenge_id}" in ids
    assert f"skill:{skill_id}" in ids
    assert any(node["type"] == "category" for node in graph["nodes"])
    relations = {(edge["source"], edge["target"], edge["relation"]) for edge in graph["edges"]}
    assert (f"challenge:{challenge_id}", f"skill:{skill_id}", "requires") in relations


# --- Recommendation impressions (H1) --------------------------------------- #

@pytest.mark.asyncio
async def test_recommendation_logging_and_same_day_dedupe(test_db):
    async with test_db() as db:
        user = User(
            id=uuid.uuid4(), keycloak_sub="rec_user", email="ru@test.com", display_name="RU"
        )
        c1 = Challenge(
            slug="c1", title="C1", description="d", category="X",
            difficulty="beginner", points=10, status="published",
        )
        c2 = Challenge(
            slug="c2", title="C2", description="d", category="X",
            difficulty="beginner", points=20, status="published",
        )
        db.add_all([user, c1, c2])
        await db.commit()

        recs1 = await get_recommendations(db, user_id=user.id, limit=10)
        assert len(recs1) == 2

        async def count_logs() -> int:
            return len((await db.scalars(select(RecommendationLog))).all())

        assert await count_logs() == 2
        await get_recommendations(db, user_id=user.id, limit=10)
        assert await count_logs() == 2


@pytest.mark.asyncio
async def test_recommendation_quality_from_logs(researcher_client, test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(research_service, "RESEARCH_DIR_OVERRIDE", tmp_path)
    client, researcher = researcher_client
    challenge_id, _ = await _seed_solved_challenge(test_db, user_id=researcher.id)

    async with test_db() as db:
        db.add(
            RecommendationLog(
                user_id=researcher.id,
                challenge_id=challenge_id,
                source="adaptive",
                generated_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        await db.commit()

    resp = await client.get("/api/v1/research/metrics")
    metrics = resp.json()
    assert metrics["recommendations"]["served"] == 1
    # The recommended challenge was already solved after the impression -> counts.
    assert metrics["recommendations"]["solved"] == 1
    assert metrics["recommendations"]["completion_rate"] == 1.0


# --- Experiment registry ---------------------------------------------------- #

@pytest.mark.asyncio
async def test_experiment_crud(researcher_client):
    client, _ = researcher_client
    created = await client.post(
        "/api/v1/research/experiments",
        json={"name": "gnn-v2", "model_ref": "GNN", "params": {"hidden": 64}},
    )
    assert created.status_code == 201, created.text
    experiment = created.json()
    assert experiment["status"] == "queued"

    listed = await client.get("/api/v1/research/experiments")
    assert len(listed.json()) == 1

    patched = await client.patch(
        f"/api/v1/research/experiments/{experiment['id']}",
        json={"status": "complete", "metrics": {"auc": 0.81}},
    )
    assert patched.status_code == 200
    assert patched.json()["metrics"]["auc"] == 0.81

    deleted = await client.delete(f"/api/v1/research/experiments/{experiment['id']}")
    assert deleted.status_code == 204
    assert len((await client.get("/api/v1/research/experiments")).json()) == 0


# --- Permission gating ------------------------------------------------------ #

@pytest.mark.asyncio
async def test_research_denied_for_student(student_client):
    client, _ = student_client
    for endpoint in (
        "/api/v1/research/metrics",
        "/api/v1/research/datasets",
        "/api/v1/research/datasets/some-id",
        "/api/v1/research/experiments",
        "/api/v1/research/graph",
    ):
        resp = await client.get(endpoint)
        assert resp.status_code == 403