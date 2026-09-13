"""Endpoint integration tests for adaptive learning routes."""

import uuid
import pytest
from app.models import Challenge, User
from app.models.learning_paths import LearningPath, LearningPathStep

@pytest.mark.asyncio
async def test_learning_paths_endpoints(student_client, test_db):
    client, user = student_client

    async with test_db() as db:
        p = LearningPath(slug="ep-path", title="EP Path", is_published=True)
        db.add(p)
        c = Challenge(slug=f"ep_{uuid.uuid4().hex[:6]}", title="EP", description="desc", category="Linux", difficulty="beginner", points=10, status="published")
        db.add(c)
        await db.flush()
        db.add(LearningPathStep(learning_path_id=p.id, challenge_id=c.id, step_order=0))
        await db.commit()

    # Public list
    res = await client.get("/api/v1/paths")
    assert res.status_code == 200
    assert len(res.json()) >= 1
    assert any(x["slug"] == "ep-path" for x in res.json())

    # Detail progress
    res = await client.get(f"/api/v1/paths/{p.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["slug"] == "ep-path"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["status"] == "unlocked"

    # Student cannot create
    res = await client.post("/api/v1/paths", json={"slug": "bad", "title": "bad", "is_published": False})
    assert res.status_code == 403

@pytest.mark.asyncio
async def test_recommendations_endpoint(student_client, test_db):
    client, user = student_client

    async with test_db() as db:
        c = Challenge(slug=f"rec_{uuid.uuid4().hex[:6]}", title="Rec Challenge", description="desc", category="Linux", difficulty="beginner", points=10, status="published")
        db.add(c)
        await db.commit()

    res = await client.get("/api/v1/recommendations/challenges?limit=5")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
