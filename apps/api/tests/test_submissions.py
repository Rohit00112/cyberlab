"""Integration tests for flag submission, scoring, and leaderboard (PRD §19-21, §23)."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.flags import hash_flag
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Challenge, User  # noqa: F401  (registers tables)

SessionFactory = async_sessionmaker[AsyncSession]

CORRECT = "IIC{test-flag}"


def _student(sub: str = "student-sub-test") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["student"],
        permissions=["challenge.view", "submission.create"],
    )


def _faculty(sub: str = "faculty-sub-test") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["faculty"],
        permissions=["challenge.view", "challenge.edit"],
    )


@pytest.fixture
async def test_db():
    url = get_settings().database_url
    test_url = f"{url.rsplit('/', 1)[0]}/cyberlab_test"
    engine = create_async_engine(test_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _make_client(factory: SessionFactory, user: CurrentUser | None = None):
    async def _db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _request_as(client, user, method, url, **kwargs):
    """Run one request as a specific user (dependency override is app-global)."""
    app.dependency_overrides[get_current_user] = lambda: user
    return await client.request(method, url, **kwargs)


async def _ensure_user(factory: SessionFactory, user: CurrentUser) -> None:
    async with factory() as db:
        existing = await db.get(User, user.id)
        if existing is None:
            db.add(
                User(
                    id=user.id,
                    keycloak_sub=user.keycloak_sub,
                    email=f"{user.keycloak_sub}@cyberlab.test",
                    display_name=f"Test {user.roles[0].title()}",
                )
            )
            await db.commit()


@pytest.fixture
async def student_client(test_db):
    user = _student()
    await _ensure_user(test_db, user)
    async with _make_client(test_db, user) as client:
        yield client, user
    app.dependency_overrides.clear()


async def _seed_challenge(
    factory: SessionFactory, *, slug: str, points: int, status: str = "published"
) -> Challenge:
    async with factory() as db:
        challenge = Challenge(
            slug=slug,
            title=f"Seed {slug}",
            description=f"Description of {slug}",
            category="Linux",
            difficulty="beginner",
            points=points,
            flag_hash=hash_flag(CORRECT),
            flag_format="IIC{...}",
            status=status,
        )
        db.add(challenge)
        await db.commit()
        await db.refresh(challenge)
        return challenge


async def _delete_by_slug(factory: SessionFactory, slug: str):
    async with factory() as db:
        challenge = await db.scalar(select(Challenge).where(Challenge.slug == slug))
        if challenge:
            await db.delete(challenge)
            await db.commit()


@pytest.mark.asyncio
async def test_correct_flag_awards_points(student_client, test_db):
    client, user = student_client
    challenge = await _seed_challenge(
        test_db, slug=f"_t_correct_{uuid.uuid4().hex[:6]}", points=100
    )
    try:
        res = await client.post(
            f"/api/v1/challenges/{challenge.id}/submissions", json={"flag": CORRECT}
        )
        assert res.status_code == 201
        body = res.json()
        assert body["correct"] is True
        assert body["points"] == 100
        assert body["already_solved"] is False

        status_res = await client.get("/api/v1/submissions/status")
        entry = status_res.json()[str(challenge.id)]
        assert entry["solved"] is True
        assert entry["points"] == 100
        assert entry["attempts"] == 1

        mine = (await client.get("/api/v1/submissions/me")).json()
        assert mine[0]["challenge_id"] == str(challenge.id)
        assert mine[0]["is_correct"] is True
        assert mine[0]["earned_points"] == 100

        stats = (await client.get("/api/v1/submissions/stats")).json()
        assert stats["points"] == 100
        assert stats["solved_count"] == 1
        assert stats["attempts"] == 1
    finally:
        await _delete_by_slug(test_db, challenge.slug)


@pytest.mark.asyncio
async def test_wrong_flag_no_points_but_logged(student_client, test_db):
    client, user = student_client
    challenge = await _seed_challenge(test_db, slug=f"_t_wrong_{uuid.uuid4().hex[:6]}", points=50)
    try:
        res = await client.post(
            f"/api/v1/challenges/{challenge.id}/submissions", json={"flag": "IIC{nope}"}
        )
        assert res.status_code == 201
        body = res.json()
        assert body["correct"] is False
        assert body["points"] == 0

        status_res = await client.get("/api/v1/submissions/status")
        entry = status_res.json()[str(challenge.id)]
        assert entry["solved"] is False
        assert entry["attempts"] == 1
        assert entry["points"] == 0
    finally:
        await _delete_by_slug(test_db, challenge.slug)


@pytest.mark.asyncio
async def test_repeat_solve_does_not_double_points(student_client, test_db):
    client, user = student_client
    challenge = await _seed_challenge(test_db, slug=f"_t_repeat_{uuid.uuid4().hex[:6]}", points=100)
    try:
        r1 = await client.post(
            f"/api/v1/challenges/{challenge.id}/submissions", json={"flag": CORRECT}
        )
        r2 = await client.post(
            f"/api/v1/challenges/{challenge.id}/submissions", json={"flag": CORRECT}
        )
        assert r1.json()["points"] == 100
        assert r2.status_code == 201
        assert r2.json()["already_solved"] is True
        assert r2.json()["points"] == 0

        status_res = await client.get("/api/v1/submissions/status")
        entry = status_res.json()[str(challenge.id)]
        assert entry["points"] == 100
        assert entry["attempts"] == 1
        stats = (await client.get("/api/v1/submissions/stats")).json()
        assert stats["points"] == 100
        assert stats["solved_count"] == 1
        assert stats["attempts"] == 1
    finally:
        await _delete_by_slug(test_db, challenge.slug)


@pytest.mark.asyncio
async def test_empty_flag_rejected(student_client, test_db):
    client, user = student_client
    challenge = await _seed_challenge(test_db, slug=f"_t_empty_{uuid.uuid4().hex[:6]}", points=100)
    try:
        res = await client.post(f"/api/v1/challenges/{challenge.id}/submissions", json={"flag": ""})
        assert res.status_code == 422
    finally:
        await _delete_by_slug(test_db, challenge.slug)


@pytest.mark.asyncio
async def test_draft_challenge_not_submittable(student_client, test_db):
    client, user = student_client
    challenge = await _seed_challenge(
        test_db, slug=f"_t_draft_{uuid.uuid4().hex[:6]}", points=100, status="draft"
    )
    try:
        res = await client.post(
            f"/api/v1/challenges/{challenge.id}/submissions", json={"flag": CORRECT}
        )
        assert res.status_code == 404
    finally:
        await _delete_by_slug(test_db, challenge.slug)


@pytest.mark.asyncio
async def test_missing_challenge_404(student_client, test_db):
    client, user = student_client
    res = await client.post(
        f"/api/v1/challenges/{uuid.uuid4()}/submissions", json={"flag": CORRECT}
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_faculty_cannot_submit(student_client, test_db):
    client, user = student_client
    faculty = _faculty()
    await _ensure_user(test_db, faculty)
    challenge = await _seed_challenge(test_db, slug=f"_t_fac_{uuid.uuid4().hex[:6]}", points=75)
    try:
        res = await _request_as(
            client,
            faculty,
            "POST",
            f"/api/v1/challenges/{challenge.id}/submissions",
            json={"flag": CORRECT},
        )
        assert res.status_code == 403
    finally:
        await _delete_by_slug(test_db, challenge.slug)


@pytest.mark.asyncio
async def test_leaderboard_order_and_rank(test_db):
    stu1 = _student("lb-far")
    stu2 = _student("lb-near")
    await _ensure_user(test_db, stu1)
    await _ensure_user(test_db, stu2)

    low = await _seed_challenge(test_db, slug=f"_t_lb_low_{uuid.uuid4().hex[:6]}", points=25)
    high = await _seed_challenge(test_db, slug=f"_t_lb_high_{uuid.uuid4().hex[:6]}", points=200)
    first = await _seed_challenge(test_db, slug=f"_t_lb_first_{uuid.uuid4().hex[:6]}", points=100)
    try:
        async with _make_client(test_db) as client:
            await _request_as(
                client,
                stu2,
                "POST",
                f"/api/v1/challenges/{low.id}/submissions",
                json={"flag": CORRECT},
            )
            await _request_as(
                client,
                stu1,
                "POST",
                f"/api/v1/challenges/{high.id}/submissions",
                json={"flag": CORRECT},
            )
            await _request_as(
                client,
                stu1,
                "POST",
                f"/api/v1/challenges/{first.id}/submissions",
                json={"flag": CORRECT},
            )

            res = await _request_as(client, stu1, "GET", "/api/v1/leaderboard")
            assert res.status_code == 200
            board = res.json()
            assert len(board) >= 2

            row1 = next(r for r in board if r["user_id"] == str(stu1.id))
            row2 = next(r for r in board if r["user_id"] == str(stu2.id))

            assert row1["points"] == 300
            assert row1["solved_count"] == 2
            assert row2["points"] == 25
            assert row2["solved_count"] == 1
            assert row1["rank"] < row2["rank"]
    finally:
        await _delete_by_slug(test_db, low.slug)
        await _delete_by_slug(test_db, high.slug)
        await _delete_by_slug(test_db, first.slug)


@pytest.mark.asyncio
async def test_leaderboard_tiebreak_by_first_solve(test_db):
    early = _student("lb-tie-early")
    late = _student("lb-tie-late")
    await _ensure_user(test_db, early)
    await _ensure_user(test_db, late)

    tie = await _seed_challenge(test_db, slug=f"_t_lb_tie_{uuid.uuid4().hex[:6]}", points=100)
    try:
        async with _make_client(test_db) as client:
            await _request_as(
                client,
                early,
                "POST",
                f"/api/v1/challenges/{tie.id}/submissions",
                json={"flag": CORRECT},
            )
            await _request_as(
                client,
                late,
                "POST",
                f"/api/v1/challenges/{tie.id}/submissions",
                json={"flag": CORRECT},
            )

            board = (await _request_as(client, early, "GET", "/api/v1/leaderboard")).json()
            row_early = next(r for r in board if r["user_id"] == str(early.id))
            row_late = next(r for r in board if r["user_id"] == str(late.id))
            assert row_early["rank"] < row_late["rank"]
    finally:
        await _delete_by_slug(test_db, tie.slug)
