"""Real Rust HTTP + PostgreSQL parity, isolated from cyberlab_test.

Run with RUN_RUST_DB_INTEGRATION=1 after building the Rust debug binary.
Creates and drops only a uniquely named disposable database. Never drops
tables in the running development database or the shared test database.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import asyncpg
import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import CurrentUser, get_current_user
from app.core import authorization, rust_engine
from app.core.config import get_settings
from app.core.flags import hash_flag
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (  # noqa: F401 (registers tables)
    AuditLog,
    Challenge,
    ChallengeSkill,
    Competition,
    CompetitionChallenge,
    Skill,
    Submission,
    User,
)
from app.services import challenges, competitions, submissions

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_RUST_DB_INTEGRATION") != "1",
        reason="opt-in: RUN_RUST_DB_INTEGRATION=1 and cargo build --locked required",
    ),
]

ROOT = Path(__file__).resolve().parents[3]
BINARY = Path(os.environ.get(
    "RUST_CORE_TEST_BINARY",
    str(ROOT / "apps/security-core/target/debug/cyberlab-security-core"),
))


@pytest.fixture
async def live_rust_database():
    if not await asyncio.to_thread(BINARY.is_file):
        pytest.fail("Rust binary missing: cd apps/security-core && cargo build --locked")

    base = get_settings().database_url
    admin_dsn = base.replace("postgresql+asyncpg://", "postgresql://", 1)
    name = f"cyberlab_rust_parity_{uuid.uuid4().hex[:16]}"
    database_dsn = f"{admin_dsn.rsplit('/', 1)[0]}/{name}"
    test_database_url = f"{base.rsplit('/', 1)[0]}/{name}"
    admin = await asyncpg.connect(admin_dsn)
    created = False
    engine = None
    server = None
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
        created = True
        engine = create_async_engine(test_database_url, pool_pre_ping=True)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            now = datetime.now(UTC)
            u1, u2, u3 = (
                User(keycloak_sub=f"parity-{uuid.uuid4().hex}", display_name=label)
                for label in ("Early", "Late", "Unsolved")
            )
            c1 = Challenge(
                slug=f"parity-pub1-{uuid.uuid4().hex}", title="Published 1",
                description="Challenge", category="Linux", difficulty="beginner",
                points=150, status="published", flag_hash="a" * 64,
            )
            c2 = Challenge(
                slug=f"parity-pub2-{uuid.uuid4().hex}", title="Published 2",
                description="Challenge", category="Web Security", difficulty="intermediate",
                points=150, status="published",
            )
            c3 = Challenge(
                slug=f"parity-draft-{uuid.uuid4().hex}", title="Draft",
                description="Hidden", category="Linux", difficulty="beginner",
                points=900, status="draft",
            )
            db.add_all([u1, u2, u3, c1, c2, c3])
            db.add(Skill(slug="linux", name="Linux"))
            await db.flush()
            db.add_all([
                Submission(
                    user_id=u1.id, challenge_id=c1.id, is_correct=True,
                    earned_points=100, created_at=now - timedelta(days=2),
                ),
                Submission(
                    user_id=u1.id, challenge_id=c2.id, is_correct=True,
                    earned_points=50, created_at=now - timedelta(days=1),
                ),
                Submission(
                    user_id=u2.id, challenge_id=c1.id, is_correct=True,
                    earned_points=150, created_at=now,
                ),
                Submission(
                    user_id=u3.id, challenge_id=c1.id, is_correct=False,
                    earned_points=0, created_at=now,
                ),
            ])
            await db.commit()
            seeded = (u1.id, u2.id, c1.id, c2.id, c3.id)

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        token = "integration-only-" + uuid.uuid4().hex + uuid.uuid4().hex
        rust_db_url = database_dsn.replace("postgresql://", "postgres://", 1)
        server = await asyncio.create_subprocess_exec(
            str(BINARY),
            env={
                **os.environ,
                "PORT": str(port),
                "RUST_CORE_SHARED_TOKEN": token,
                "SECURITY_CORE_DATABASE_URL": rust_db_url,
                "SECURITY_CORE_WRITE_DATABASE_URL": rust_db_url,
            },
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        rust_url = f"http://127.0.0.1:{port}"
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            for _ in range(50):
                if server.returncode is not None:
                    pytest.fail("Rust process exited before serving requests")
                try:
                    response = await client.get(f"{rust_url}/ready")
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.1)
            else:
                pytest.fail("Rust service database readiness endpoint never became ready")

        yield SimpleNamespace(
            factory=factory, rust_url=rust_url, token=token,
            seeded=seeded,
        )
    finally:
        if server is not None:
            server.terminate()
            try:
                await asyncio.wait_for(server.wait(), timeout=3)
            except TimeoutError:
                server.kill()
                await server.wait()
        if engine is not None:
            await engine.dispose()
        if created:
            await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


async def test_live_catalog_and_leaderboard_api_match_python(
    live_rust_database, monkeypatch
):
    ctx = live_rust_database
    u1, u2, c1, c2, c3 = ctx.seeded
    settings = SimpleNamespace(
        rust_core_url=ctx.rust_url,
        rust_core_shared_token=ctx.token,
    )
    # The API's normal database dependencies use this dedicated database.
    # Switching facades allows an actual Python vs Rust comparison.
    async def get_test_db():
        async with ctx.factory() as db:
            yield db

    app.dependency_overrides[get_db] = get_test_db
    user = CurrentUser(id=u1, keycloak_sub="test", roles=["student"])
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(rust_engine, "get_settings", lambda: settings)
    monkeypatch.setattr(authorization, "get_settings", lambda: settings)
    monkeypatch.setattr(challenges, "get_settings", lambda: settings)
    monkeypatch.setattr(submissions, "get_settings", lambda: settings)
    try:
        async with ctx.factory() as db:
            settings.rust_core_url = ""
            python_board = [
                entry.model_dump(mode="json")
                for entry in await submissions.leaderboard(db, limit=10)
            ]
            python_student, python_total = await challenges.list_challenges(
                db, ["student"], limit=1, offset=0
            )
            python_editor, editor_total = await challenges.list_challenges(
                db, ["faculty"], limit=10
            )
        assert python_total == 2 and editor_total == 3
        assert python_board[0]["user_id"] == str(u1)
        assert python_board[1]["user_id"] == str(u2)
        assert python_board[0]["points"] == python_board[1]["points"] == 150
        assert python_board[0]["solved_count"] == 2

        settings.rust_core_url = ctx.rust_url
        async with ctx.factory() as db:
            rust_board = [
                entry.model_dump(mode="json")
                for entry in await submissions.leaderboard(db, limit=10)
            ]
            rust_student, rust_total = await challenges.list_challenges(
                db, ["student"], limit=1, offset=0
            )
            rust_editor, rust_editor_total = await challenges.list_challenges(
                db, ["faculty"], limit=10
            )
        assert rust_board == python_board
        assert rust_total == python_total
        assert [entry.id for entry in rust_student] == [
            entry.id for entry in python_student
        ]
        assert rust_editor_total == editor_total
        assert [entry.id for entry in rust_editor] == [
            entry.id for entry in python_editor
        ]

        # A forged status filter cannot return drafts to students.
        ids, total = await rust_engine.catalog_page(
            editor=False, status="draft", category=None,
            difficulty=None, limit=10, offset=0,
        )
        assert total == 2 and str(c3) not in ids
        assert set(ids) == {str(c1), str(c2)}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            board_response = await client.get("/api/v1/leaderboard")
            assert board_response.status_code == 200
            assert board_response.json() == python_board
            challenges_response = await client.get("/api/v1/challenges?limit=1")
            assert challenges_response.status_code == 200
            assert len(challenges_response.json()) == 1
            assert challenges_response.json()[0]["id"] != str(c3)

        async with httpx.AsyncClient(timeout=2) as client:
            health = await client.get(f"{ctx.rust_url}/health")
            assert health.status_code == 200
            ready = await client.get(f"{ctx.rust_url}/ready")
            assert ready.status_code == 200
            # Internal endpoints are never anonymous.
            missing_token = await client.post(
                f"{ctx.rust_url}/v1/leaderboard", json={"limit": 10}
            )
            assert missing_token.status_code == 401
            bad_limit = await client.post(
                f"{ctx.rust_url}/v1/leaderboard",
                json={"limit": 0}, headers={"x-internal-token": ctx.token},
            )
            assert bad_limit.status_code == 400
            publish_url = f"{ctx.rust_url}/v1/challenges/publish"
            payload = {
                "challenge_id": str(c1),
                "actor_id": str(u1),
                "roles": ["faculty"],
                "ip_address": "127.0.0.1",
            }
            denied = await client.post(publish_url, json={**payload, "roles": ["student"]},
                                       headers={"x-internal-token": ctx.token})
            assert denied.status_code == 403
            first = await client.post(publish_url, json=payload,
                                      headers={"x-internal-token": ctx.token})
            assert first.status_code == 200 and first.json()["outcome"] == "published"
            second = await client.post(publish_url, json=payload,
                                       headers={"x-internal-token": ctx.token})
            assert second.status_code == 200
            assert second.json()["version"] == first.json()["version"] + 1
            missing_flag = await client.post(
                publish_url, json={**payload, "challenge_id": str(c2)},
                headers={"x-internal-token": ctx.token},
            )
            assert missing_flag.status_code == 200
            assert missing_flag.json()["outcome"] == "missing_flag"
            forbidden_delete = await client.post(
                f"{ctx.rust_url}/v1/challenges/delete",
                json={**payload, "challenge_id": str(c3), "roles": ["student"]},
                headers={"x-internal-token": ctx.token},
            )
            assert forbidden_delete.status_code == 403
            forbidden_create = await client.post(
                f"{ctx.rust_url}/v1/challenges/create",
                json={
                    "actor_id": str(u1), "roles": ["student"], "ip_address": None,
                    "slug": "forbidden-creation", "fields": {
                        "title": "Forbidden", "description": "No creation allowed",
                        "category": "Linux", "difficulty": "beginner",
                    },
                },
                headers={"x-internal-token": ctx.token},
            )
            assert forbidden_create.status_code == 403
            incorrect_url = f"{ctx.rust_url}/v1/submissions/incorrect"
            attempt_payload = {
                "challenge_id": str(c1), "user_id": str(u2),
                "roles": ["student"], "ip_address": "127.0.0.1",
            }
            forbidden_attempt = await client.post(
                incorrect_url, json={**attempt_payload, "roles": []},
                headers={"x-internal-token": ctx.token},
            )
            assert forbidden_attempt.status_code == 403
            persisted_attempt = await client.post(
                incorrect_url, json=attempt_payload,
                headers={"x-internal-token": ctx.token},
            )
            assert persisted_attempt.status_code == 200
            assert persisted_attempt.json()["outcome"] == "recorded"
        async with ctx.factory() as db:
            published = await db.get(Challenge, c1)
            assert published.version == 3
            assert await db.scalar(
                select(func.count()).select_from(Submission)
                .where(Submission.challenge_id == c1, Submission.user_id == u2,
                       Submission.is_correct.is_(False))
            ) == 1
            assert await db.scalar(
                select(func.count()).select_from(AuditLog)
                .where(AuditLog.event == "submission.attempt", AuditLog.user_id == u2)
            ) == 1
            assert await db.scalar(
                select(func.count()).select_from(AuditLog)
                .where(AuditLog.event == "challenge.publish", AuditLog.user_id == u1)
            ) == 2
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id=u1, keycloak_sub="test", roles=["faculty"]
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            published_response = await client.post(f"/api/v1/challenges/{c1}/publish")
            assert published_response.status_code == 200
            assert published_response.json()["version"] == 4
            missing_response = await client.post(f"/api/v1/challenges/{c2}/publish")
            assert missing_response.status_code == 400
            edited = await client.patch(
                f"/api/v1/challenges/{c1}",
                json={"title": "Rust Edited", "points": 180, "skills": ["Linux CLI"]},
            )
            assert edited.status_code == 200, edited.text
            assert edited.json()["title"] == "Rust Edited"
            assert edited.json()["version"] == 5
            assert edited.json()["points"] == 180
            blocked_status = await client.patch(
                f"/api/v1/challenges/{c1}", json={"status": "draft"}
            )
            assert blocked_status.status_code == 400
            creation_payload = {
                "title": "Rust Atomic Creation", "description": "Created through Rust",
                "category": "Linux", "difficulty": "beginner",
                "points": 75, "hint_penalty": 12, "skills": ["Linux CLI"],
                "flag": "IIC{creation}",
            }
            created_response = await client.post(
                "/api/v1/challenges", json=creation_payload,
            )
            assert created_response.status_code == 201, created_response.text
            created = created_response.json()
            created_id = uuid.UUID(created["id"])
            assert created["status"] == "draft"
            assert created["version"] == 1
            assert created["hint_penalty"] == 12
            assert created["slug"] == "rust-atomic-creation"
            duplicate = await client.post(
                "/api/v1/challenges", json=creation_payload,
            )
            assert duplicate.status_code == 201, duplicate.text
            assert duplicate.json()["id"] != created["id"]
            assert duplicate.json()["slug"].startswith("rust-atomic-creation-")
            deleted_response = await client.delete(f"/api/v1/challenges/{c3}")
            assert deleted_response.status_code == 204
            repeated_delete = await client.delete(f"/api/v1/challenges/{c3}")
            assert repeated_delete.status_code == 404
        async with ctx.factory() as db:
            created_row = await db.get(Challenge, created_id)
            assert created_row.flag_hash == hash_flag("IIC{creation}")
            assert created_row.hint_penalty == 12
            assert await db.scalar(
                select(func.count()).select_from(ChallengeSkill)
                .where(ChallengeSkill.challenge_id == created_id)
            ) == 1
            assert await db.scalar(
                select(func.count()).select_from(AuditLog)
                .where(AuditLog.event == "challenge.create", AuditLog.user_id == u1)
            ) == 2
            assert await db.get(Challenge, c3) is None
            assert await db.scalar(
                select(func.count()).select_from(AuditLog)
                .where(AuditLog.event == "challenge.publish", AuditLog.user_id == u1)
            ) == 3
            assert await db.scalar(
                select(func.count()).select_from(AuditLog)
                .where(AuditLog.event == "challenge.delete", AuditLog.user_id == u1)
            ) == 1
            assert await db.scalar(
                select(func.count()).select_from(AuditLog)
                .where(AuditLog.event == "challenge.update", AuditLog.user_id == u1)
            ) == 1

        # Correct solves must persist the submission, score ledger, competency
        # and audit together, and never award a second solve.
        async with ctx.factory() as db:
            solve_challenge = Challenge(
                slug=f"rust-solve-{uuid.uuid4().hex}",
                title="Rust solve", description="Atomic score",
                category="Linux", difficulty="beginner",
                points=120, hint_penalty=20, status="published",
                flag_hash=hash_flag("IIC{atomic-solve}"),
            )
            db.add(solve_challenge)
            await db.flush()
            solve_id = solve_challenge.id
            skill = await db.scalar(select(Skill).where(Skill.slug == "linux"))
            db.add(ChallengeSkill(challenge_id=solve_id, skill_id=skill.id))
            await db.commit()
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id=u2, keycloak_sub="solve-test", roles=["student"]
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            solve_path = f"/api/v1/challenges/{solve_id}/submissions"
            solve = await client.post(solve_path, json={"flag": "IIC{atomic-solve}"})
            assert solve.status_code == 201, solve.text
            assert solve.json()["points"] == 120
            repeat = await client.post(solve_path, json={"flag": "IIC{atomic-solve}"})
            assert repeat.status_code == 201
            assert repeat.json()["already_solved"] is True
            assert repeat.json()["points"] == 0
        async with ctx.factory() as db:
            from app.models import ScoreEvent, UserSkillProfile
            assert await db.scalar(
                select(func.count()).select_from(Submission)
                .where(Submission.user_id == u2, Submission.challenge_id == solve_id,
                       Submission.is_correct.is_(True))
            ) == 1
            event = await db.scalar(
                select(ScoreEvent).where(
                    ScoreEvent.user_id == u2, ScoreEvent.challenge_id == solve_id
                )
            )
            assert event.points == 120 and event.is_first_blood
            profile = await db.scalar(
                select(UserSkillProfile).where(
                    UserSkillProfile.user_id == u2, UserSkillProfile.skill_id == skill.id
                )
            )
            assert profile.competency_level == 5.0
            assert await db.scalar(
                select(func.count()).select_from(AuditLog)
                .where(AuditLog.user_id == u2, AuditLog.event == "submission.solve")
            ) == 1
        async with httpx.AsyncClient(timeout=2) as client:
            solve_url = f"{ctx.rust_url}/v1/submissions/correct"
            solve_payload = {
                "challenge_id": str(solve_id), "user_id": str(u1),
                "roles": ["student"], "ip_address": None,
                "candidate": "IIC{atomic-solve}", "lab_id": None,
            }
            denied_solve = await client.post(
                solve_url, json={**solve_payload, "roles": []},
                headers={"x-internal-token": ctx.token},
            )
            assert denied_solve.status_code == 403
            stale = await client.post(
                solve_url, json={**solve_payload, "candidate": "IIC{wrong}"},
                headers={"x-internal-token": ctx.token},
            )
            assert stale.status_code == 200
            assert stale.json()["outcome"] == "stale_flag"

            # Concurrent requests from the same user must award exactly once.
            concurrent = await asyncio.gather(*(
                client.post(
                    solve_url, json={
                        **solve_payload, "user_id": str(u1),
                    }, headers={"x-internal-token": ctx.token},
                ) for _ in range(2)
            ))
            assert all(reply.status_code == 200 for reply in concurrent)
            assert {reply.json()["outcome"] for reply in concurrent} == {
                "solved", "already_solved"
            }
        async with ctx.factory() as db:
            assert await db.scalar(
                select(func.count()).select_from(Submission)
                .where(Submission.challenge_id == solve_id, Submission.user_id == u1,
                       Submission.is_correct.is_(True))
            ) == 1
            assert await db.scalar(
                select(func.count()).select_from(ScoreEvent)
                .where(ScoreEvent.challenge_id == solve_id, ScoreEvent.user_id == u1)
            ) == 1

        # A broken audit INSERT must abort the entire solve transaction.
        async with ctx.factory() as db:
            rollback_user = User(
                keycloak_sub=f"rollback-solve-{uuid.uuid4().hex}", display_name="Rollback"
            )
            db.add(rollback_user)
            await db.flush()
            rollback_user_id = rollback_user.id
            await db.commit()
            await db.execute(text(
                "ALTER TABLE audit_logs ADD CONSTRAINT audit_block_solve "
                "CHECK (event <> 'submission.solve') NOT VALID"
            ))
            await db.commit()
        async with httpx.AsyncClient(timeout=2) as client:
            failed_solve = await client.post(
                solve_url, json={**solve_payload, "user_id": str(rollback_user_id)},
                headers={"x-internal-token": ctx.token},
            )
            assert failed_solve.status_code == 503
        async with ctx.factory() as db:
            assert await db.scalar(
                select(func.count()).select_from(Submission)
                .where(Submission.challenge_id == solve_id, Submission.user_id == rollback_user_id,
                       Submission.is_correct.is_(True))
            ) == 0
            assert await db.scalar(
                select(func.count()).select_from(ScoreEvent)
                .where(ScoreEvent.challenge_id == solve_id, ScoreEvent.user_id == rollback_user_id)
            ) == 0

        # Force an audit-insert failure in the disposable DB. The corresponding
        # challenge mutation must roll back, rather than publish without audit.
        async with ctx.factory() as db:
            rollback_challenge = Challenge(
                slug=f"rollback-{uuid.uuid4().hex}",
                title="Rollback challenge",
                description="Audit must commit with publication",
                category="Linux",
                difficulty="beginner",
                points=25,
                status="draft",
                flag_hash="b" * 64,
            )
            db.add(rollback_challenge)
            await db.flush()
            rollback_id = rollback_challenge.id
            await db.commit()
            await db.execute(text(
                "ALTER TABLE audit_logs ADD CONSTRAINT audit_block_publish "
                "CHECK (event <> 'challenge.publish') NOT VALID"
            ))
            await db.commit()
        async with httpx.AsyncClient(timeout=2) as client:
            failed_publish = await client.post(
                f"{ctx.rust_url}/v1/challenges/publish",
                json={**payload, "challenge_id": str(rollback_id)},
                headers={"x-internal-token": ctx.token},
            )
            assert failed_publish.status_code == 503
        async with ctx.factory() as db:
            row = await db.get(Challenge, rollback_id)
            assert row.status == "draft"
            assert row.version == 1
            await db.execute(text(
                "ALTER TABLE audit_logs ADD CONSTRAINT audit_block_create "
                "CHECK (event <> 'challenge.create') NOT VALID"
            ))
            await db.commit()
        async with httpx.AsyncClient(timeout=2) as client:
            failed_create = await client.post(
                f"{ctx.rust_url}/v1/challenges/create",
                json={
                    "actor_id": str(u1), "roles": ["faculty"], "ip_address": None,
                    "slug": "creation-must-rollback", "fields": {
                        "title": "Creation must rollback",
                        "description": "Audit insertion is rejected",
                        "category": "Linux", "difficulty": "beginner",
                        "skills": ["Linux CLI"],
                    },
                },
                headers={"x-internal-token": ctx.token},
            )
            assert failed_create.status_code == 503
        async with ctx.factory() as db:
            assert await db.scalar(
                select(func.count()).select_from(Challenge)
                .where(Challenge.slug == "creation-must-rollback")
            ) == 0
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


async def test_rust_competition_creation_is_atomic_and_api_compatible(
    live_rust_database, monkeypatch
):
    ctx = live_rust_database
    organizer_id, _, _, _, _ = ctx.seeded
    settings = SimpleNamespace(
        rust_core_url=ctx.rust_url, rust_core_shared_token=ctx.token,
    )
    monkeypatch.setattr(rust_engine, "get_settings", lambda: settings)
    monkeypatch.setattr(authorization, "get_settings", lambda: settings)
    monkeypatch.setattr(competitions, "get_settings", lambda: settings)

    async def get_test_db():
        async with ctx.factory() as db:
            yield db

    app.dependency_overrides[get_db] = get_test_db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=organizer_id, keycloak_sub="competition-test", roles=["faculty"],
    )
    payload = {
        "title": "Autumn CTF", "description": "Atomic creation",
        "max_team_size": 5, "allow_teams": True,
    }
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            first = await client.post("/api/v1/competitions", json=payload)
            assert first.status_code == 201, first.text
            created = first.json()
            assert created["title"] == payload["title"]
            assert created["status"] == "draft"
            assert created["max_team_size"] == 5
            assert created["allow_teams"] is True

            second = await client.post("/api/v1/competitions", json=payload)
            assert second.status_code == 201, second.text
            assert second.json()["slug"].startswith("autumn-ctf-")
            assert second.json()["id"] != created["id"]

        async with ctx.factory() as db:
            assert await db.scalar(
                select(func.count()).select_from(Competition)
                .where(Competition.title == payload["title"])
            ) == 2
            assert await db.scalar(
                select(func.count()).select_from(AuditLog)
                .where(AuditLog.event == "competition.create",
                       AuditLog.user_id == organizer_id)
            ) == 2

        # Exercise the exact restricted columns needed by Rust SQL's
        # INSERT ... ON CONFLICT ... RETURNING id, not just the owner connection.
        # The test-only NOLOGIN role, grants and inserted rows all roll back.
        probe_role = f"cyberlab_comp_probe_{uuid.uuid4().hex[:12]}"
        async with ctx.factory() as db:
            try:
                await db.execute(text(f'CREATE ROLE "{probe_role}" NOLOGIN'))
                await db.execute(text(f'GRANT USAGE ON SCHEMA public TO "{probe_role}"'))
                await db.execute(text(
                    f'GRANT INSERT (id, slug, title, description, rules, start_at, '
                    'end_at, registration_ends_at, allow_teams, max_team_size, '
                    'scoring_mode, status, created_by, freeze_leaderboard) '
                    f'ON public.competitions TO "{probe_role}"'
                ))
                await db.execute(text(
                    f'GRANT SELECT (id, slug) ON public.competitions TO "{probe_role}"'
                ))
                await db.execute(text(
                    'GRANT INSERT (id, event, user_id, target_id, ip_address) '
                    f'ON public.audit_logs TO "{probe_role}"'
                ))
                await db.execute(text(f'SET LOCAL ROLE "{probe_role}"'))
                inserted = await db.scalar(text(
                    "INSERT INTO competitions "
                    "(id, slug, title, status, created_by, freeze_leaderboard, "
                    "allow_teams, max_team_size, scoring_mode) "
                    "VALUES (gen_random_uuid(), 'restricted-ctf', 'Restricted', "
                    "'draft', :actor_id, false, false, 4, 'standard') "
                    "ON CONFLICT (slug) DO NOTHING RETURNING id::text"
                ), {"actor_id": organizer_id})
                assert inserted is not None
                await db.execute(text(
                    "INSERT INTO audit_logs (id, event, user_id, target_id) "
                    "VALUES (gen_random_uuid(), 'competition.create', "
                    ":actor_id, 'restricted-ctf')"
                ), {"actor_id": organizer_id})
            finally:
                await db.rollback()

        internal = f"{ctx.rust_url}/v1/competitions/create"
        rust_payload = {
            "actor_id": str(organizer_id),
            "roles": ["student"], "ip_address": None,
            "slug": "forbidden-ctf", "fields": {"title": "Forbidden CTF"},
        }
        async with httpx.AsyncClient(timeout=2) as client:
            unauthorized = await client.post(internal, json=rust_payload)
            assert unauthorized.status_code == 401
            denied = await client.post(
                internal, json=rust_payload,
                headers={"x-internal-token": ctx.token},
            )
            assert denied.status_code == 403
            malformed = await client.post(
                internal, json={
                    **rust_payload, "roles": ["faculty"],
                    "fields": {"title": "Invalid", "status": "live"},
                }, headers={"x-internal-token": ctx.token},
            )
            assert malformed.status_code == 400

        # Force audit failure only on this disposable database. The new
        # competition must not survive without its mandatory audit record.
        async with ctx.factory() as db:
            await db.execute(text(
                "ALTER TABLE audit_logs ADD CONSTRAINT block_competition_create "
                "CHECK (event <> 'competition.create') NOT VALID"
            ))
            await db.commit()
        async with httpx.AsyncClient(timeout=2) as client:
            failed = await client.post(
                internal, json={
                    **rust_payload, "roles": ["faculty"],
                    "slug": "audit-must-rollback",
                    "fields": {"title": "Must rollback"},
                }, headers={"x-internal-token": ctx.token},
            )
            assert failed.status_code == 503
        async with ctx.factory() as db:
            assert await db.scalar(
                select(func.count()).select_from(Competition)
                .where(Competition.slug == "audit-must-rollback")
            ) == 0
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


async def test_rust_competition_edit_is_atomic_and_api_compatible(
    live_rust_database, monkeypatch
):
    ctx = live_rust_database
    organizer_id, _, _, _, _ = ctx.seeded
    settings = SimpleNamespace(
        rust_core_url=ctx.rust_url, rust_core_shared_token=ctx.token,
    )
    monkeypatch.setattr(rust_engine, "get_settings", lambda: settings)
    monkeypatch.setattr(authorization, "get_settings", lambda: settings)
    monkeypatch.setattr(competitions, "get_settings", lambda: settings)

    async def get_test_db():
        async with ctx.factory() as db:
            yield db

    app.dependency_overrides[get_db] = get_test_db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=organizer_id, keycloak_sub="edit-test", roles=["faculty"],
    )
    async with ctx.factory() as db:
        competition = Competition(
            slug="edit-ctf", title="Before edit", status="draft",
            created_by=organizer_id, description="Original",
        )
        rollback_competition = Competition(
            slug="edit-rollback-ctf", title="Must stay original", status="draft",
            created_by=organizer_id,
        )
        db.add_all([competition, rollback_competition])
        await db.commit()
        competition_id, rollback_id = competition.id, rollback_competition.id

    internal = f"{ctx.rust_url}/v1/competitions/edit"
    rust_payload = {
        "competition_id": str(competition_id), "actor_id": str(organizer_id),
        "roles": ["faculty"], "ip_address": "127.0.0.1",
        "changes": {"title": "From Rust"},
    }
    try:
        start = datetime.now(UTC) + timedelta(days=1)
        end = start + timedelta(hours=2)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            first = await client.patch(
                f"/api/v1/competitions/{competition_id}",
                json={
                    "title": "From Rust", "description": "Updated",
                    "start_at": start.isoformat(), "end_at": end.isoformat(),
                    "allow_teams": True, "max_team_size": 6,
                },
            )
            assert first.status_code == 200, first.text
            assert first.json()["title"] == "From Rust"
            assert first.json()["slug"] == "edit-ctf"
            assert first.json()["status"] == "draft"
            assert first.json()["max_team_size"] == 6
            assert first.json()["allow_teams"] is True

            cleared = await client.patch(
                f"/api/v1/competitions/{competition_id}",
                json={"description": None, "rules": "New rules"},
            )
            assert cleared.status_code == 200, cleared.text
            assert cleared.json()["description"] is None
            # The existing PATCH response deliberately hides draft rules.
            assert cleared.json()["rules"] is None

            invalid_dates = await client.patch(
                f"/api/v1/competitions/{competition_id}",
                json={"start_at": end.isoformat(), "end_at": start.isoformat()},
            )
            assert invalid_dates.status_code == 400

        async with ctx.factory() as db:
            persisted = await db.get(Competition, competition_id)
            assert persisted.title == "From Rust"
            assert persisted.description is None
            assert persisted.rules == "New rules"
            assert persisted.start_at == start
            assert persisted.end_at == end
            assert await db.scalar(
                select(func.count()).select_from(AuditLog)
                .where(AuditLog.event == "competition.update",
                       AuditLog.target_id == "edit-ctf")
            ) == 2

        async with httpx.AsyncClient(timeout=2) as client:
            unauthorized = await client.post(internal, json=rust_payload)
            assert unauthorized.status_code == 401
            forbidden = await client.post(
                internal, json={**rust_payload, "roles": ["student"]},
                headers={"x-internal-token": ctx.token},
            )
            assert forbidden.status_code == 403
            forbidden_field = await client.post(
                internal, json={**rust_payload, "changes": {"status": "live"}},
                headers={"x-internal-token": ctx.token},
            )
            assert forbidden_field.status_code == 400
            invalid_timestamp = await client.post(
                internal, json={**rust_payload, "changes": {"start_at": "nonsense"}},
                headers={"x-internal-token": ctx.token},
            )
            assert invalid_timestamp.status_code == 400
            invalid_order = await client.post(
                internal, json={**rust_payload, "changes": {
                    "start_at": end.isoformat(), "end_at": start.isoformat(),
                }}, headers={"x-internal-token": ctx.token},
            )
            assert invalid_order.status_code == 400

        # Prove the edit SQL works with only the intended SELECT/UPDATE columns.
        # CREATE ROLE and all grants disappear when this transaction rolls back.
        probe = f"cyberlab_edit_probe_{uuid.uuid4().hex[:12]}"
        async with ctx.factory() as db:
            try:
                await db.execute(text(f'CREATE ROLE "{probe}" NOLOGIN'))
                await db.execute(text(f'GRANT USAGE ON SCHEMA public TO "{probe}"'))
                await db.execute(text(
                    f'GRANT SELECT (id, slug, status) ON competitions TO "{probe}"'
                ))
                await db.execute(text(
                    'GRANT UPDATE (title, description, rules, start_at, end_at, '
                    'registration_ends_at, allow_teams, max_team_size, scoring_mode, '
                    f'updated_at) ON competitions TO "{probe}"'
                ))
                await db.execute(text(
                    'GRANT INSERT (id, event, user_id, target_id, ip_address) '
                    f'ON audit_logs TO "{probe}"'
                ))
                await db.execute(text(f'SET LOCAL ROLE "{probe}"'))
                locked = await db.execute(text(
                    "SELECT slug, status FROM competitions WHERE id=:id FOR UPDATE"
                ), {"id": competition_id})
                assert locked.first() == ("edit-ctf", "draft")
                await db.execute(text(
                    "UPDATE competitions SET title='Privilege probe', updated_at=now() "
                    "WHERE id=:id"
                ), {"id": competition_id})
                await db.execute(text(
                    "INSERT INTO audit_logs (id, event, user_id, target_id) "
                    "VALUES (gen_random_uuid(), 'competition.update', :actor, 'edit-ctf')"
                ), {"actor": organizer_id})
            finally:
                await db.rollback()

        async with ctx.factory() as db:
            locked_competition = await db.get(Competition, competition_id)
            assert locked_competition.title == "From Rust"
            locked_competition.status = "live"
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            locked_public = await client.patch(
                f"/api/v1/competitions/{competition_id}",
                json={"title": "Must not change"},
            )
            assert locked_public.status_code == 409
        async with httpx.AsyncClient(timeout=2) as client:
            locked_internal = await client.post(
                internal, json=rust_payload,
                headers={"x-internal-token": ctx.token},
            )
            assert locked_internal.status_code == 200
            assert locked_internal.json()["outcome"] == "locked"

        async with ctx.factory() as db:
            await db.execute(text(
                "ALTER TABLE audit_logs ADD CONSTRAINT block_competition_update "
                "CHECK (event <> 'competition.update') NOT VALID"
            ))
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            failure = await client.patch(
                f"/api/v1/competitions/{rollback_id}",
                json={"title": "Should roll back"},
            )
            assert failure.status_code == 503
        async with ctx.factory() as db:
            row = await db.get(Competition, rollback_id)
            assert row.title == "Must stay original"
            assert await db.scalar(
                select(func.count()).select_from(AuditLog)
                .where(AuditLog.event == "competition.update")
            ) == 2
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


async def test_rust_competition_challenge_links_are_atomic_and_api_compatible(
    live_rust_database, monkeypatch
):
    ctx = live_rust_database
    organizer_id, _, published_id, another_published_id, draft_id = ctx.seeded
    settings = SimpleNamespace(
        rust_core_url=ctx.rust_url, rust_core_shared_token=ctx.token,
    )
    monkeypatch.setattr(rust_engine, "get_settings", lambda: settings)
    monkeypatch.setattr(authorization, "get_settings", lambda: settings)
    monkeypatch.setattr(competitions, "get_settings", lambda: settings)

    async def get_test_db():
        async with ctx.factory() as db:
            yield db

    app.dependency_overrides[get_db] = get_test_db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=organizer_id, keycloak_sub="link-test", roles=["faculty"],
    )
    async with ctx.factory() as db:
        override_comp = Competition(
            slug="link-override", title="Override links", status="draft",
            scoring_mode="override", created_by=organizer_id,
        )
        standard_comp = Competition(
            slug="link-standard", title="Standard links", status="registration",
            scoring_mode="standard", created_by=organizer_id,
        )
        rollback_comp = Competition(
            slug="link-rollback", title="Rollback links", status="draft",
            created_by=organizer_id,
        )
        db.add_all([override_comp, standard_comp, rollback_comp])
        await db.commit()
        override_id, standard_id, rollback_id = (
            override_comp.id, standard_comp.id, rollback_comp.id
        )

    add_route = f"{ctx.rust_url}/v1/competitions/challenges/add"
    remove_route = f"{ctx.rust_url}/v1/competitions/challenges/remove"
    rust_payload = {
        "competition_id": str(override_id), "challenge_id": str(published_id),
        "actor_id": str(organizer_id), "roles": ["faculty"],
        "ip_address": "127.0.0.1", "points": 125,
    }
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            link_url = f"/api/v1/competitions/{override_id}/challenges"
            first = await client.post(
                link_url, json={"challenge_id": str(published_id), "points": 125}
            )
            assert first.status_code == 200, first.text
            assert first.json()["challenge_count"] == 1
            assert first.json()["challenges"][0]["position"] == 0
            assert first.json()["challenges"][0]["points"] == 125

            second = await client.post(
                link_url, json={"challenge_id": str(another_published_id)}
            )
            assert second.status_code == 200, second.text
            assert [item["position"] for item in second.json()["challenges"]] == [0, 1]
            duplicate = await client.post(
                link_url, json={"challenge_id": str(published_id), "points": 99}
            )
            assert duplicate.status_code == 409
            unpublished = await client.post(
                link_url, json={"challenge_id": str(draft_id)}
            )
            assert unpublished.status_code == 404

            standard = await client.post(
                f"/api/v1/competitions/{standard_id}/challenges",
                json={"challenge_id": str(published_id), "points": 888},
            )
            assert standard.status_code == 200, standard.text
            assert standard.json()["challenges"][0]["points"] is None

            removed = await client.delete(f"{link_url}/{published_id}")
            assert removed.status_code == 200, removed.text
            assert removed.json()["challenge_count"] == 1
            assert removed.json()["challenges"][0]["position"] == 1
            repeated = await client.delete(f"{link_url}/{published_id}")
            assert repeated.status_code == 200
            assert repeated.json()["challenge_count"] == 1

        async with ctx.factory() as db:
            assert await db.scalar(
                select(func.count()).select_from(AuditLog)
                .where(AuditLog.event == "competition.challenge_add")
            ) == 3
            assert await db.scalar(
                select(func.count()).select_from(AuditLog)
                .where(AuditLog.event == "competition.challenge_remove")
            ) == 2
            stored = await db.scalar(
                select(CompetitionChallenge).where(
                    CompetitionChallenge.competition_id == override_id,
                    CompetitionChallenge.challenge_id == another_published_id,
                )
            )
            assert stored.position == 1 and stored.points is None

        async with httpx.AsyncClient(timeout=2) as client:
            unauthorized = await client.post(add_route, json=rust_payload)
            assert unauthorized.status_code == 401
            forbidden = await client.post(
                add_route, json={**rust_payload, "roles": ["student"]},
                headers={"x-internal-token": ctx.token},
            )
            assert forbidden.status_code == 403
            invalid_points = await client.post(
                add_route, json={**rust_payload, "points": -1},
                headers={"x-internal-token": ctx.token},
            )
            assert invalid_points.status_code == 400
            invalid_id = await client.post(
                remove_route, json={**rust_payload, "challenge_id": "invalid"},
                headers={"x-internal-token": ctx.token},
            )
            assert invalid_id.status_code == 400

        # Probe the column allowlists inside a rolled-back transaction, without
        # provisioning or touching persistent database roles.
        role = f"cyberlab_link_probe_{uuid.uuid4().hex[:12]}"
        async with ctx.factory() as db:
            try:
                await db.execute(text(f'CREATE ROLE "{role}" NOLOGIN'))
                await db.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
                await db.execute(text(
                    f'GRANT SELECT (id, slug, status, scoring_mode) ON competitions TO "{role}"'
                ))
                # FOR UPDATE requires a column-scoped UPDATE privilege too;
                # the real writer already has one from competition editing.
                await db.execute(text(
                    f'GRANT UPDATE (title) ON competitions TO "{role}"'
                ))
                await db.execute(text(
                    f'GRANT SELECT (id, status) ON challenges TO "{role}"'
                ))
                await db.execute(text(
                    'GRANT SELECT (id, competition_id, challenge_id, position) '
                    f'ON competition_challenges TO "{role}"'
                ))
                await db.execute(text(
                    'GRANT INSERT (id, competition_id, challenge_id, points, position) '
                    f'ON competition_challenges TO "{role}"'
                ))
                await db.execute(text(
                    f'GRANT DELETE ON competition_challenges TO "{role}"'
                ))
                await db.execute(text(
                    'GRANT INSERT (id, event, user_id, target_id, ip_address, details) '
                    f'ON audit_logs TO "{role}"'
                ))
                await db.execute(text(f'SET LOCAL ROLE "{role}"'))
                await db.execute(text(
                    'SELECT slug, status, scoring_mode FROM competitions '
                    'WHERE id=:id FOR UPDATE'
                ), {"id": override_id})
                pos = await db.scalar(text(
                    'SELECT COALESCE(MAX(position), -1) FROM competition_challenges '
                    'WHERE competition_id=:id'
                ), {"id": override_id})
                assert pos == 1
                inserted = await db.scalar(text(
                    'INSERT INTO competition_challenges '
                    '(id, competition_id, challenge_id, points, position) '
                    'VALUES (gen_random_uuid(), :cid, :chid, 17, 2) '
                    'ON CONFLICT (competition_id, challenge_id) DO NOTHING '
                    'RETURNING id::text'
                ), {"cid": override_id, "chid": published_id})
                assert inserted is not None
                await db.execute(text(
                    'DELETE FROM competition_challenges WHERE competition_id=:cid '
                    'AND challenge_id=:chid'
                ), {"cid": override_id, "chid": published_id})
                await db.execute(text(
                    'INSERT INTO audit_logs '
                    '(id, event, user_id, target_id, details) VALUES '
                    '(gen_random_uuid(), :event, :actor, :target, :details)'
                ), {
                    "event": "competition.challenge_add", "actor": organizer_id,
                    "target": str(published_id), "details": '{"competition":"link-override"}',
                })
            finally:
                await db.rollback()

        async with ctx.factory() as db:
            locked = await db.get(Competition, override_id)
            locked.status = "scheduled"
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            refused = await client.post(
                f"/api/v1/competitions/{override_id}/challenges",
                json={"challenge_id": str(published_id)},
            )
            assert refused.status_code == 409
        async with httpx.AsyncClient(timeout=2) as client:
            locked_rust = await client.post(
                remove_route, json=rust_payload,
                headers={"x-internal-token": ctx.token},
            )
            assert locked_rust.status_code == 200
            assert locked_rust.json()["outcome"] == "locked"

        # A mandatory audit failure rolls back both add and remove operations.
        async with ctx.factory() as db:
            await db.execute(text(
                "ALTER TABLE audit_logs ADD CONSTRAINT block_link_add "
                "CHECK (event <> 'competition.challenge_add') NOT VALID"
            ))
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            rollback_add = await client.post(
                f"/api/v1/competitions/{rollback_id}/challenges",
                json={"challenge_id": str(published_id)},
            )
            assert rollback_add.status_code == 503
        async with ctx.factory() as db:
            assert await db.scalar(select(func.count()).select_from(CompetitionChallenge)
                .where(CompetitionChallenge.competition_id == rollback_id)) == 0
            await db.execute(text("ALTER TABLE audit_logs DROP CONSTRAINT block_link_add"))
            db.add(CompetitionChallenge(
                competition_id=rollback_id, challenge_id=published_id,
                position=0,
            ))
            await db.commit()
            await db.execute(text(
                "ALTER TABLE audit_logs ADD CONSTRAINT block_link_remove "
                "CHECK (event <> 'competition.challenge_remove') NOT VALID"
            ))
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            rollback_remove = await client.delete(
                f"/api/v1/competitions/{rollback_id}/challenges/{published_id}"
            )
            assert rollback_remove.status_code == 503
        async with ctx.factory() as db:
            assert await db.scalar(select(func.count()).select_from(CompetitionChallenge)
                .where(CompetitionChallenge.competition_id == rollback_id)) == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
