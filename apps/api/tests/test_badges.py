"""Tests for badge management, catalogue, and automatic awarding (PRD §34)."""
import uuid

import pytest
from sqlalchemy import select

from app.models.badges import Badge, UserBadge
from app.models.challenges import Challenge
from app.models.notifications import Notification
from app.models.submissions import Submission
from app.services.badges import grant_eligible_badges


@pytest.mark.asyncio
async def test_list_badges_catalogue(student_client, test_db):
    client, _ = student_client
    async with test_db() as db:
        badge = Badge(
            code="test_badge_1",
            name="Test Explorer",
            description="Explore the lab.",
            icon="🧪",
            criteria={"code": "first_solve"},
            is_active=True,
        )
        db.add(badge)
        await db.commit()

    resp = await client.get("/api/v1/badges")
    assert resp.status_code == 200
    data = resp.json()
    assert any(b["code"] == "test_badge_1" for b in data)


@pytest.mark.asyncio
async def test_my_badges_empty_then_earned(student_client, test_db):
    client, user = student_client
    resp = await client.get("/api/v1/badges/me")
    assert resp.status_code == 200
    assert resp.json() == []

    async with test_db() as db:
        badge = Badge(
            code="test_badge_earned",
            name="Earned Medal",
            description="Great job.",
            icon="🎖️",
            criteria={"code": "first_solve"},
            is_active=True,
        )
        db.add(badge)
        await db.commit()
        await db.refresh(badge)

        user_badge = UserBadge(
            user_id=user.id,
            badge_id=badge.id,
            evidence={"refs": ["first solve"]},
        )
        db.add(user_badge)
        await db.commit()

    resp = await client.get("/api/v1/badges/me")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["code"] == "test_badge_earned"
    assert items[0]["name"] == "Earned Medal"


@pytest.mark.asyncio
async def test_admin_badge_crud(student_client, test_db):
    client, user = student_client
    user.roles = ["faculty"]
    user.permissions = ["badge.manage", "badge.view"]

    # 1. Create badge
    create_payload = {
        "code": "admin_test_badge",
        "name": "Admin Created Badge",
        "description": "Created via API",
        "icon": "⚡",
        "criteria": {"code": "solver_n", "value": 10},
        "is_active": True,
    }
    resp = await client.post("/api/v1/admin/badges", json=create_payload)
    assert resp.status_code == 201
    created = resp.json()
    badge_id = created["id"]
    assert created["code"] == "admin_test_badge"

    # 2. List admin badges (includes inactive)
    resp = await client.get("/api/v1/admin/badges")
    assert resp.status_code == 200
    assert any(b["id"] == badge_id for b in resp.json())

    # 3. Update badge
    resp = await client.patch(
        f"/api/v1/admin/badges/{badge_id}",
        json={"name": "Updated Badge Title", "is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Badge Title"
    assert resp.json()["is_active"] is False

    # 4. Public list hides inactive
    resp = await client.get("/api/v1/badges")
    assert resp.status_code == 200
    assert not any(b["id"] == badge_id for b in resp.json())

    # 5. Delete badge
    resp = await client.delete(f"/api/v1/admin/badges/{badge_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_grant_eligible_badges_and_notification(test_db):
    user_id = uuid.uuid4()
    async with test_db() as db:
        # Create user
        from app.models.users import User

        db.add(
            User(
                id=user_id,
                keycloak_sub=f"sub-{user_id}",
                email="badgeuser@test.local",
                display_name="Badge User",
            )
        )
        # Create challenge & correct solve
        challenge = Challenge(
            slug="badge-challenge-1",
            title="Badge Challenge",
            description="desc",
            category="Web Security",
            difficulty="beginner",
            points=100,
            flag_hash="abc",
            status="published",
        )
        db.add(challenge)
        await db.commit()
        await db.refresh(challenge)

        sub = Submission(
            user_id=user_id,
            challenge_id=challenge.id,
            is_correct=True,
            earned_points=100,
        )
        db.add(sub)

        # Create badge for first solve
        badge = Badge(
            code="first_solve",
            name="First Flag",
            description="Solved first challenge.",
            icon="🚩",
            criteria={"code": "first_solve"},
            is_active=True,
        )
        db.add(badge)
        await db.commit()

        # Run grant
        result = await grant_eligible_badges(db, user_id)
        assert "first_solve" in result.granted

        # Verify UserBadge
        user_badge = await db.scalar(
            select(UserBadge).where(UserBadge.user_id == user_id, UserBadge.badge_id == badge.id)
        )
        assert user_badge is not None

        # Verify Notification generated
        notification = await db.scalar(select(Notification).where(Notification.user_id == user_id))
        assert notification is not None
        assert "Badge Unlocked" in notification.title
        assert notification.source == "badge"
