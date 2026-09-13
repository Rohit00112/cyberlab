"""Integration tests for faculty submission review + analytics (PRD §7.2, §50)."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.flags import hash_flag
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Challenge, Submission, User  # noqa: F401  (registers tables)

SessionFactory = async_sessionmaker[AsyncSession]

CORRECT = "IIC{test-flag}"


def _student(sub: str = "student-analytics-test") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["student"],
        permissions=["challenge.view", "submission.create"],
    )


def _faculty(sub: str = "faculty-analytics-test") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["faculty"],
        permissions=[
            "challenge.view",
            "submission.review",
            "analytics.view",
        ],
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


async def _seed_challenge(
    factory: SessionFactory, *, slug: str, points: int
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
            status="published",
        )
        db.add(challenge)
        await db.commit()
        await db.refresh(challenge)
        return challenge


async def _seed_submission(
    factory: SessionFactory,
    *,
    challenge: Challenge,
    user: User,
    is_correct: bool,
    earned_points: int = 0,
) -> None:
    async with factory() as db:
        db.add(
            Submission(
                challenge_id=challenge.id,
                user_id=user.id,
                is_correct=is_correct,
                earned_points=earned_points,
            )
        )
        await db.commit()


@pytest.fixture
async def faculty_client(test_db):
    user = _faculty()
    await _ensure_user(test_db, user)
    async with _make_client(test_db, user) as client:
        yield client, user
    app.dependency_overrides.clear()


@pytest.fixture
async def student_client(test_db):
    user = _student()
    await _ensure_user(test_db, user)
    async with _make_client(test_db, user) as client:
        yield client, user
    app.dependency_overrides.clear()


async def test_review_rejected_for_student(student_client):
    client, _ = student_client
    res = await client.get("/api/v1/submissions/review")
    assert res.status_code == 403


async def test_review_rejected_for_anonymous(test_db):
    async with _make_client(test_db) as client:
        res = await client.get("/api/v1/submissions/review")
    assert res.status_code == 401


async def test_review_lists_submissions_newest_first(faculty_client, test_db):
    client, faculty = faculty_client
    challenge = await _seed_challenge(
        test_db, slug=f"_r_{uuid.uuid4().hex[:6]}", points=50
    )
    student = _student(sub=f"review-student-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, student)
    async with test_db() as db:
        student_row = await db.get(User, student.id)
    await _seed_submission(
        test_db,
        challenge=challenge,
        user=student_row,
        is_correct=False,
        earned_points=0,
    )
    await _seed_submission(
        test_db,
        challenge=challenge,
        user=student_row,
        is_correct=True,
        earned_points=50,
    )
    res = await client.get("/api/v1/submissions/review")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 2
    assert rows[0]["is_correct"] is True
    assert rows[0]["earned_points"] == 50
    assert rows[0]["display_name"] == f"Test {student.roles[0].title()}"
    assert rows[0]["challenge_title"] == f"Seed {challenge.slug}"
    assert rows[1]["is_correct"] is False


async def test_review_respects_limit_offset(faculty_client, test_db):
    client, faculty = faculty_client
    student = _student(sub=f"review-page-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, student)
    async with test_db() as db:
        student_row = await db.get(User, student.id)
    slugs = [f"_p_{i}_{uuid.uuid4().hex[:4]}" for i in range(3)]
    challenges = [await _seed_challenge(test_db, slug=s, points=10) for s in slugs]
    for c in challenges:
        await _seed_submission(
            test_db, challenge=c, user=student_row, is_correct=True, earned_points=10
        )
    res = await client.get("/api/v1/submissions/review", params={"limit": 2, "offset": 1})
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 2


async def test_analytics_rejected_for_student(student_client):
    client, _ = student_client
    res = await client.get("/api/v1/analytics/summary")
    assert res.status_code == 403


async def test_analytics_summary_aggregates(faculty_client, test_db):
    client, faculty = faculty_client
    c_a = await _seed_challenge(test_db, slug=f"_a_{uuid.uuid4().hex[:6]}", points=100)
    c_b = await _seed_challenge(test_db, slug=f"_b_{uuid.uuid4().hex[:6]}", points=50)
    student = _student(sub=f"analytics-student-{uuid.uuid4().hex[:6]}")
    await _ensure_user(test_db, student)
    async with test_db() as db:
        student_row = await db.get(User, student.id)
    # 3 attempts on A (1 solve), 1 attempt on B (0 solves)
    await _seed_submission(
        test_db, challenge=c_a, user=student_row, is_correct=True, earned_points=100
    )
    await _seed_submission(test_db, challenge=c_a, user=student_row, is_correct=False)
    await _seed_submission(test_db, challenge=c_a, user=student_row, is_correct=False)
    await _seed_submission(test_db, challenge=c_b, user=student_row, is_correct=False)

    res = await client.get("/api/v1/analytics/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["total_users"] >= 1
    assert data["total_submissions"] == 4
    assert data["total_solves"] == 1
    assert data["total_points_awarded"] == 100
    assert 0.24 < data["success_rate"] < 0.26
    top = {row["slug"]: row for row in data["top_challenges"]}
    assert top[c_a.slug]["attempts"] == 3
    assert top[c_a.slug]["solves"] == 1
    assert top[c_b.slug]["solves"] == 0
    assert data["top_students"][0]["points"] == 100
    assert data["top_students"][0]["solved_count"] == 1


@pytest.mark.asyncio
async def test_analytics_healthy_when_no_data(faculty_client):
    client, _ = faculty_client
    res = await client.get("/api/v1/analytics/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["total_submissions"] == 0
    assert data["success_rate"] == 0.0
    assert data["top_challenges"] == []
    assert data["top_students"] == []


@pytest.mark.asyncio
async def test_review_healthy_when_no_data(faculty_client):
    client, _ = faculty_client
    res = await client.get("/api/v1/submissions/review")
    assert res.status_code == 200
    assert res.json() == []