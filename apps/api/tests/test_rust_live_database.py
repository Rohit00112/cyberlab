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
from unittest.mock import AsyncMock

import asyncpg
import httpx
import pytest
from fastapi import HTTPException
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
    CompetitionParticipant,
    LabInstance,
    ProvisioningJob,
    Skill,
    Submission,
    Team,
    TeamMember,
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


async def test_rust_provisioning_claim_worker_handoff_and_atomic_rollback(
    live_rust_database, monkeypatch
):
    """Native Rust claims a disposable job; provider I/O stays in mocked Python."""
    from app.core import lab_transitions
    from app.tasks import provisioning

    ctx = live_rust_database
    owner_id, other_id, challenge_id, _, _ = ctx.seeded
    settings = SimpleNamespace(
        rust_core_url=ctx.rust_url, rust_core_shared_token=ctx.token,
    )
    monkeypatch.setattr(rust_engine, "get_settings", lambda: settings)
    monkeypatch.setattr(provisioning, "get_settings", lambda: settings)
    monkeypatch.setattr(lab_transitions, "get_settings", lambda: settings)
    monkeypatch.setattr(provisioning, "SessionLocal", ctx.factory)

    async with ctx.factory() as db:
        racing_lab = LabInstance(
            user_id=owner_id, challenge_id=challenge_id, status="queued",
            network_name="cyberlab-rust-claim-test",
        )
        worker_lab = LabInstance(
            user_id=owner_id, challenge_id=challenge_id, status="queued",
            network_name="cyberlab-rust-claim-worker",
        )
        stopped_lab = LabInstance(
            user_id=owner_id, challenge_id=challenge_id, status="stopped",
        )
        mismatched_lab = LabInstance(
            user_id=owner_id, challenge_id=challenge_id, status="queued",
        )
        rollback_lab = LabInstance(
            user_id=owner_id, challenge_id=challenge_id, status="queued",
        )
        db.add_all([racing_lab, worker_lab, stopped_lab, mismatched_lab, rollback_lab])
        await db.flush()
        racing = ProvisioningJob(
            lab_instance_id=racing_lab.id, user_id=owner_id,
            challenge_id=challenge_id, status="pending",
        )
        worker = ProvisioningJob(
            lab_instance_id=worker_lab.id, user_id=owner_id,
            challenge_id=challenge_id, status="pending",
            config={"image": "alpine:3.20", "expiry_minutes": 30},
        )
        stopped = ProvisioningJob(
            lab_instance_id=stopped_lab.id, user_id=owner_id,
            challenge_id=challenge_id, status="pending",
        )
        mismatch = ProvisioningJob(
            lab_instance_id=mismatched_lab.id, user_id=other_id,
            challenge_id=challenge_id, status="pending",
        )
        rollback = ProvisioningJob(
            lab_instance_id=rollback_lab.id, user_id=owner_id,
            challenge_id=challenge_id, status="pending",
        )
        db.add_all([racing, worker, stopped, mismatch, rollback])
        await db.commit()
        racing_id, worker_id = racing.id, worker.id
        stopped_id, mismatch_id, rollback_id = stopped.id, mismatch.id, rollback.id
        racing_lab_id, worker_lab_id = racing_lab.id, worker_lab.id
        rollback_lab_id = rollback_lab.id

    endpoint = f"{ctx.rust_url}/v1/labs/provisioning/claim"
    headers = {"x-internal-token": ctx.token}
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        payload = {"job_id": str(racing_id)}
        assert (await client.post(endpoint, json=payload)).status_code == 401
        assert (await client.post(
            endpoint, json={"job_id": "not-uuid"}, headers=headers,
        )).status_code == 400
        assert (await client.post(
            endpoint, json={"job_id": str(uuid.uuid4())}, headers=headers,
        )).json() == {"outcome": "unavailable"}

        async def request_claim():
            return await client.post(endpoint, json=payload, headers=headers)

        concurrent = await asyncio.gather(request_claim(), request_claim())
        assert all(result.status_code == 200 for result in concurrent)
        assert sorted(result.json()["outcome"] for result in concurrent) == [
            "claimed", "unavailable",
        ]
        for rejected in (stopped_id, mismatch_id):
            result = await client.post(
                endpoint, json={"job_id": str(rejected)}, headers=headers,
            )
            assert result.status_code == 200
            assert result.json() == {"outcome": "unavailable"}

    async with ctx.factory() as db:
        claimed = await db.get(ProvisioningJob, racing_id)
        claimed_lab = await db.get(LabInstance, racing_lab_id)
        assert claimed.status == "running" and claimed.started_at is not None
        assert claimed_lab.status == "provisioning"
        assert (await db.get(ProvisioningJob, stopped_id)).status == "failed"
        assert (await db.get(ProvisioningJob, mismatch_id)).status == "failed"
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "lab.provisioning.reject",
        )) == 2
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "lab.provisioning.claim",
            AuditLog.target_id == str(racing_lab_id),
        )) == 1

    start_endpoint = f"{ctx.rust_url}/v1/labs/provisioning/start"
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        start_payload = {"job_id": str(racing_id)}
        assert (await client.post(start_endpoint, json=start_payload)).status_code == 401
        assert (await client.post(
            start_endpoint, json={"job_id": "invalid"}, headers=headers,
        )).status_code == 400
        response = await client.post(start_endpoint, json=start_payload, headers=headers)
        assert response.status_code == 200 and response.json() == {"outcome": "started"}
        again = await client.post(start_endpoint, json=start_payload, headers=headers)
        assert again.json() == {"outcome": "unavailable"}
    async with ctx.factory() as db:
        assert (await db.get(LabInstance, racing_lab_id)).status == "starting"
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "lab.provisioning.start",
            AuditLog.target_id == str(racing_lab_id),
        )) == 1

    # Probe the SQL using only disposable column-scoped grants, not the DB owner.
    probe = f"cyberlab_claim_probe_{uuid.uuid4().hex[:10]}"
    async with ctx.factory() as db:
        try:
            await db.execute(text(f'CREATE ROLE "{probe}" NOLOGIN'))
            await db.execute(text(f'GRANT USAGE ON SCHEMA public TO "{probe}"'))
            await db.execute(text(
                'GRANT SELECT (id, lab_instance_id, user_id, challenge_id, status) '
                f'ON provisioning_jobs TO "{probe}"'
            ))
            await db.execute(text(
                'GRANT UPDATE (status, started_at, completed_at, error_message, updated_at) '
                f'ON provisioning_jobs TO "{probe}"'
            ))
            await db.execute(text(
                'GRANT SELECT (id, user_id, challenge_id, status) '
                f'ON lab_instances TO "{probe}"'
            ))
            await db.execute(text(
                'GRANT UPDATE (status, updated_at, provider_ref, container_id, '
                'container_name, flag_hash, flag_path, connection_hint, '
                'error_message, expires_at) '
                f'ON lab_instances TO "{probe}"'
            ))
            await db.execute(text(
                'GRANT INSERT (id, event, user_id, target_id, details) '
                f'ON audit_logs TO "{probe}"'
            ))
            await db.execute(text(f'SET LOCAL ROLE "{probe}"'))
            row = (await db.execute(text(
                "SELECT lab_instance_id::text, user_id::text, challenge_id::text "
                "FROM provisioning_jobs WHERE id = :job_id AND status = 'pending' "
                "FOR UPDATE SKIP LOCKED"
            ), {"job_id": worker_id})).one()
            locked_lab = (await db.execute(text(
                "SELECT user_id::text, challenge_id::text, status "
                "FROM lab_instances WHERE id = :lab_id FOR UPDATE SKIP LOCKED"
            ), {"lab_id": worker_lab_id})).one()
            assert row[1] == locked_lab[0] and row[2] == locked_lab[1]
            assert locked_lab[2] == "queued"
            await db.execute(text(
                "UPDATE provisioning_jobs SET status = 'running', "
                "started_at = now(), updated_at = now() WHERE id = :job_id"
            ), {"job_id": worker_id})
            await db.execute(text(
                "UPDATE lab_instances SET status = 'provisioning', updated_at = now() "
                "WHERE id = :lab_id"
            ), {"lab_id": worker_lab_id})
            await db.execute(text(
                "INSERT INTO audit_logs (id, event, user_id, target_id) "
                "VALUES (gen_random_uuid(), 'lab.provisioning.claim', :uid, :lid)"
            ), {"uid": owner_id, "lid": str(worker_lab_id)})
            await db.execute(text(
                "UPDATE lab_instances SET status = 'starting', updated_at = now() "
                "WHERE id = :lab_id"
            ), {"lab_id": worker_lab_id})
            await db.execute(text(
                "INSERT INTO audit_logs (id, event, user_id, target_id) "
                "VALUES (gen_random_uuid(), 'lab.provisioning.start', :uid, :lid)"
            ), {"uid": owner_id, "lid": str(worker_lab_id)})
            await db.execute(text(
                "UPDATE provisioning_jobs SET status = 'failed', completed_at = now(), "
                "error_message = 'Lab no longer queued', updated_at = now() "
                "WHERE id = :job_id"
            ), {"job_id": worker_id})
            await db.execute(text(
                "INSERT INTO audit_logs (id, event, user_id, target_id) "
                "VALUES (gen_random_uuid(), 'lab.provisioning.reject', :uid, :lid)"
            ), {"uid": owner_id, "lid": str(worker_lab_id)})
            await db.execute(text(
                "UPDATE lab_instances SET provider_ref = 'mock-provider-ref', "
                "container_id = 'mock-provider-ref', container_name = 'lab-mock', "
                "flag_hash = :flag_hash, flag_path = '/flag.txt', "
                "connection_hint = 'mock endpoint', error_message = NULL, "
                "expires_at = now() + interval '30 minutes' WHERE id = :lab_id"
            ), {"lab_id": worker_lab_id, "flag_hash": "b" * 64})
            await db.execute(text(
                "INSERT INTO audit_logs (id, event, user_id, target_id, details) "
                "VALUES (gen_random_uuid(), 'lab.provisioning.failure', :uid, "
                ":lid, CAST(:details AS jsonb))"
            ), {"uid": owner_id, "lid": str(worker_lab_id),
                "details": '{"cleanup_failed": true}'})
        finally:
            await db.rollback()

    # Full worker handoff must never call a real infrastructure provider.
    fake_provider = SimpleNamespace(
        ensure_network=AsyncMock(),
        create_lab=AsyncMock(return_value=("mock-provider-ref", "192.0.2.10")),
    )
    monkeypatch.setattr(provisioning, "get_lab_provider", lambda _name: fake_provider)
    assert await provisioning.execute_provisioning_job(str(worker_id)) is True
    assert await provisioning.execute_provisioning_job(str(worker_id)) is False
    fake_provider.create_lab.assert_awaited_once()
    async with ctx.factory() as db:
        finished_job = await db.get(ProvisioningJob, worker_id)
        finished_lab = await db.get(LabInstance, worker_lab_id)
        assert finished_job.status == "completed"
        assert finished_lab.status == "running"
        assert finished_lab.provider_ref == "mock-provider-ref"
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "lab.provisioning.claim",
            AuditLog.target_id == str(worker_lab_id),
        )) == 1
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "lab.provisioning.start",
            AuditLog.target_id == str(worker_lab_id),
        )) == 1
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "lab.provisioning.complete",
            AuditLog.target_id == str(worker_lab_id),
        )) == 1

    complete_endpoint = f"{ctx.rust_url}/v1/labs/provisioning/complete"
    fail_endpoint = f"{ctx.rust_url}/v1/labs/provisioning/fail"
    complete_payload = {
        "job_id": str(worker_id), "provider_ref": "mock-provider-ref",
        "container_name": "lab-mock", "flag_hash": "a" * 64,
        "flag_path": "/flag.txt", "connection_hint": "mock endpoint",
        "expiry_minutes": 30,
    }
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        assert (await client.post(complete_endpoint, json=complete_payload)).status_code == 401
        assert (await client.post(
            complete_endpoint, json={**complete_payload, "flag_hash": "not-hex"},
            headers=headers,
        )).status_code == 400
        assert (await client.post(
            complete_endpoint, json=complete_payload, headers=headers,
        )).json() == {"outcome": "unavailable"}

    async with ctx.factory() as db:
        failed_lab = LabInstance(
            user_id=owner_id, challenge_id=challenge_id, status="queued",
        )
        db.add(failed_lab)
        await db.flush()
        failed_job = ProvisioningJob(
            lab_instance_id=failed_lab.id, user_id=owner_id,
            challenge_id=challenge_id, status="pending",
        )
        db.add(failed_job)
        await db.commit()
        failed_job_id, failed_lab_id = failed_job.id, failed_lab.id
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        for route, outcome in ((endpoint, "claimed"), (start_endpoint, "started")):
            response = await client.post(
                route, json={"job_id": str(failed_job_id)}, headers=headers,
            )
            assert response.status_code == 200 and response.json() == {"outcome": outcome}
        failed_payload = {
            "job_id": str(failed_job_id), "error_message": "provider unavailable",
            "cleanup_failed": True, "provider_ref": "orphaned-vm",
        }
        assert (await client.post(
            fail_endpoint, json={**failed_payload, "provider_ref": None},
            headers=headers,
        )).status_code == 400
        response = await client.post(fail_endpoint, json=failed_payload, headers=headers)
        assert response.status_code == 200 and response.json() == {"outcome": "failed"}
        assert (await client.post(
            fail_endpoint, json=failed_payload, headers=headers,
        )).json() == {"outcome": "unavailable"}
    async with ctx.factory() as db:
        failed_state = await db.get(LabInstance, failed_lab_id)
        assert failed_state.status == "failed"
        assert failed_state.provider_ref == "orphaned-vm"
        assert failed_state.container_id == "orphaned-vm"
        assert (await db.get(ProvisioningJob, failed_job_id)).status == "failed"
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "lab.provisioning.failure",
            AuditLog.target_id == str(failed_lab_id),
        )) == 1

    # Mandatory audit failure rolls back both job and lab state; no partial
    # terminal transition may escape the Rust transaction.
    async with ctx.factory() as db:
        failure_rollback_lab = LabInstance(
            user_id=owner_id, challenge_id=challenge_id, status="queued",
        )
        db.add(failure_rollback_lab)
        await db.flush()
        failure_rollback_job = ProvisioningJob(
            lab_instance_id=failure_rollback_lab.id, user_id=owner_id,
            challenge_id=challenge_id, status="pending",
        )
        db.add(failure_rollback_job)
        await db.commit()
        failure_rollback_id = failure_rollback_job.id
        failure_rollback_lab_id = failure_rollback_lab.id
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        for route, expected in ((endpoint, "claimed"), (start_endpoint, "started")):
            response = await client.post(
                route, json={"job_id": str(failure_rollback_id)}, headers=headers,
            )
            assert response.status_code == 200
            assert response.json() == {"outcome": expected}
    async with ctx.factory() as db:
        await db.execute(text(
            "ALTER TABLE audit_logs ADD CONSTRAINT block_lab_failure "
            "CHECK (event <> 'lab.provisioning.failure') NOT VALID"
        ))
        await db.commit()
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        response = await client.post(
            fail_endpoint, headers=headers, json={
                "job_id": str(failure_rollback_id),
                "error_message": "provider failure",
                "cleanup_failed": False, "provider_ref": None,
            },
        )
        assert response.status_code == 503
    async with ctx.factory() as db:
        assert (await db.get(LabInstance, failure_rollback_lab_id)).status == "starting"
        assert (await db.get(ProvisioningJob, failure_rollback_id)).status == "running"
        await db.execute(text(
            "ALTER TABLE audit_logs DROP CONSTRAINT block_lab_failure"
        ))
        await db.commit()

    # The starting transition must also roll back if its audit cannot persist.
    async with ctx.factory() as db:
        start_rollback_lab = LabInstance(
            user_id=owner_id, challenge_id=challenge_id, status="queued",
        )
        db.add(start_rollback_lab)
        await db.flush()
        start_rollback_job = ProvisioningJob(
            lab_instance_id=start_rollback_lab.id, user_id=owner_id,
            challenge_id=challenge_id, status="pending",
        )
        db.add(start_rollback_job)
        await db.commit()
        start_rollback_id = start_rollback_job.id
        start_rollback_lab_id = start_rollback_lab.id
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        initial = await client.post(
            endpoint, json={"job_id": str(start_rollback_id)}, headers=headers,
        )
        assert initial.json() == {"outcome": "claimed"}
    async with ctx.factory() as db:
        await db.execute(text(
            "ALTER TABLE audit_logs ADD CONSTRAINT block_lab_start "
            "CHECK (event <> 'lab.provisioning.start') NOT VALID"
        ))
        await db.commit()
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        failed_start = await client.post(
            start_endpoint, json={"job_id": str(start_rollback_id)}, headers=headers,
        )
        assert failed_start.status_code == 503
    async with ctx.factory() as db:
        assert (await db.get(LabInstance, start_rollback_lab_id)).status == "provisioning"
        assert (await db.get(ProvisioningJob, start_rollback_id)).status == "running"
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "lab.provisioning.start",
            AuditLog.target_id == str(start_rollback_lab_id),
        )) == 0

    # A Rust start failure must not be converted into a Python status write or
    # start the provider. The test resumes an already-claimed job deliberately.
    with monkeypatch.context() as patcher:
        patcher.setattr(
            rust_engine, "claim_provisioning_job_in_rust", AsyncMock(return_value=True),
        )
        with pytest.raises(HTTPException) as exc:
            await provisioning.execute_provisioning_job(str(start_rollback_id))
        assert exc.value.status_code == 503
    fake_provider.create_lab.assert_awaited_once()
    async with ctx.factory() as db:
        assert (await db.get(LabInstance, start_rollback_lab_id)).status == "provisioning"
        assert (await db.get(ProvisioningJob, start_rollback_id)).status == "running"

    async with ctx.factory() as db:
        await db.execute(text(
            "ALTER TABLE audit_logs ADD CONSTRAINT block_lab_claim "
            "CHECK (event <> 'lab.provisioning.claim') NOT VALID"
        ))
        await db.commit()
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        result = await client.post(
            endpoint, json={"job_id": str(rollback_id)}, headers=headers,
        )
        assert result.status_code == 503
    async with ctx.factory() as db:
        assert (await db.get(ProvisioningJob, rollback_id)).status == "pending"
        assert (await db.get(LabInstance, rollback_lab_id)).status == "queued"
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "lab.provisioning.claim",
            AuditLog.target_id == str(rollback_lab_id),
        )) == 0

    # A failed audit also blocks the worker before it can call any provider.
    with pytest.raises(HTTPException) as exc:
        await provisioning.execute_provisioning_job(str(rollback_id))
    assert exc.value.status_code == 503
    fake_provider.create_lab.assert_awaited_once()


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


async def test_rust_competition_registration_is_atomic_and_api_compatible(
    live_rust_database, monkeypatch
):
    ctx = live_rust_database
    student_id, another_student_id, _, _, _ = ctx.seeded
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
        id=student_id, keycloak_sub="registration-test", roles=["student"],
    )
    async with ctx.factory() as db:
        active = Competition(
            slug="registration-open", title="Registration open",
            status="registration", allow_teams=True, created_by=student_id,
        )
        closed = Competition(
            slug="registration-closed", title="Registration closed",
            status="draft", created_by=student_id,
        )
        rollback_comp = Competition(
            slug="registration-rollback", title="Registration rollback",
            status="scheduled", created_by=student_id,
        )
        db.add_all([active, closed, rollback_comp])
        await db.commit()
        active_id, closed_id, rollback_id = active.id, closed.id, rollback_comp.id

    register_internal = f"{ctx.rust_url}/v1/competitions/register"
    unregister_internal = f"{ctx.rust_url}/v1/competitions/unregister"
    request_data = {
        "competition_id": str(active_id), "actor_id": str(student_id),
        "roles": ["student"], "ip_address": "127.0.0.1",
    }
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            registered = await client.post(
                f"/api/v1/competitions/{active_id}/register"
            )
            assert registered.status_code == 200, registered.text
            assert registered.json()["participant_count"] == 1
            assert registered.json()["me"]["registered"] is True
            duplicate = await client.post(
                f"/api/v1/competitions/{active_id}/register"
            )
            assert duplicate.status_code == 409
            assert duplicate.json()["detail"] == "Already registered"
            closed = await client.post(
                f"/api/v1/competitions/{closed_id}/register"
            )
            assert closed.status_code == 409
            assert "draft" in closed.json()["detail"]

        async with httpx.AsyncClient(timeout=2) as client:
            missing_token = await client.post(register_internal, json=request_data)
            assert missing_token.status_code == 401
            missing_unregistration_token = await client.post(
                unregister_internal, json=request_data
            )
            assert missing_unregistration_token.status_code == 401
            forbidden = await client.post(
                register_internal,
                json={**request_data, "roles": ["competition_organizer"]},
                headers={"x-internal-token": ctx.token},
            )
            assert forbidden.status_code == 403
            forbidden_unregistration = await client.post(
                unregister_internal,
                json={**request_data, "roles": ["competition_organizer"]},
                headers={"x-internal-token": ctx.token},
            )
            assert forbidden_unregistration.status_code == 403
            invalid_id = await client.post(
                register_internal,
                json={**request_data, "actor_id": "invalid"},
                headers={"x-internal-token": ctx.token},
            )
            assert invalid_id.status_code == 400
            direct_closed = await client.post(
                register_internal,
                json={**request_data, "competition_id": str(closed_id)},
                headers={"x-internal-token": ctx.token},
            )
            assert direct_closed.status_code == 200
            assert direct_closed.json()["outcome"] == "closed"
            assert direct_closed.json()["current_status"] == "draft"

        # Test the minimal database privileges without persisting a role.
        probe = f"cyberlab_registration_probe_{uuid.uuid4().hex[:10]}"
        async with ctx.factory() as db:
            try:
                await db.execute(text(f'CREATE ROLE "{probe}" NOLOGIN'))
                await db.execute(text(f'GRANT USAGE ON SCHEMA public TO "{probe}"'))
                await db.execute(text(
                    f'GRANT SELECT (id, slug, status) ON competitions TO "{probe}"'
                ))
                await db.execute(text(
                    f'GRANT UPDATE (title) ON competitions TO "{probe}"'
                ))
                await db.execute(text(
                    'GRANT SELECT (id, competition_id, user_id, team_id) '
                    f'ON competition_participants TO "{probe}"'
                ))
                await db.execute(text(
                    'GRANT INSERT (id, competition_id, user_id) '
                    f'ON competition_participants TO "{probe}"'
                ))
                await db.execute(text(
                    f'GRANT DELETE ON competition_participants TO "{probe}"'
                ))
                await db.execute(text(
                    f'GRANT SELECT (team_id, user_id) ON team_members TO "{probe}"'
                ))
                await db.execute(text(
                    f'GRANT DELETE ON team_members TO "{probe}"'
                ))
                await db.execute(text(
                    'GRANT INSERT (id, event, user_id, target_id, ip_address) '
                    f'ON audit_logs TO "{probe}"'
                ))
                await db.execute(text(f'SET LOCAL ROLE "{probe}"'))
                await db.execute(text(
                    'SELECT slug, status FROM competitions WHERE id=:cid FOR UPDATE'
                ), {"cid": rollback_id})
                inserted = await db.scalar(text(
                    'INSERT INTO competition_participants (id, competition_id, user_id) '
                    'VALUES (gen_random_uuid(), :cid, :uid) '
                    'ON CONFLICT (competition_id, user_id) DO NOTHING RETURNING id::text'
                ), {"cid": rollback_id, "uid": another_student_id})
                assert inserted is not None
                team_id = await db.scalar(text(
                    'SELECT team_id::text FROM competition_participants '
                    'WHERE competition_id=:cid AND user_id=:uid'
                ), {"cid": rollback_id, "uid": another_student_id})
                assert team_id is None
                await db.execute(text(
                    'DELETE FROM competition_participants '
                    'WHERE competition_id=:cid AND user_id=:uid'
                ), {"cid": rollback_id, "uid": another_student_id})
                await db.execute(text(
                    'INSERT INTO audit_logs (id, event, user_id, target_id) '
                    "VALUES (gen_random_uuid(), 'competition.register', :actor, "
                    "'registration-rollback')"
                ), {"actor": another_student_id})
            finally:
                await db.rollback()

        # The legacy API permits unregistering even after the event goes live;
        # remove existing team membership in the same transaction.
        async with ctx.factory() as db:
            team = Team(competition_id=active_id, name="Existing team", created_by=student_id)
            db.add(team)
            await db.flush()
            db.add(TeamMember(team_id=team.id, user_id=student_id, role="captain"))
            participant = await db.scalar(select(CompetitionParticipant).where(
                CompetitionParticipant.competition_id == active_id,
                CompetitionParticipant.user_id == student_id,
            ))
            participant.team_id = team.id
            active = await db.get(Competition, active_id)
            active.status = "live"
            await db.commit()
            team_id = team.id
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            removed = await client.post(
                f"/api/v1/competitions/{active_id}/unregister"
            )
            assert removed.status_code == 200, removed.text
            assert removed.json()["participant_count"] == 0
            assert removed.json()["me"] is None
            repeated = await client.post(
                f"/api/v1/competitions/{active_id}/unregister"
            )
            assert repeated.status_code == 409
            assert repeated.json()["detail"] == "Not registered"
        async with ctx.factory() as db:
            assert await db.scalar(select(func.count()).select_from(TeamMember)
                .where(TeamMember.team_id == team_id)) == 0
            assert await db.scalar(select(func.count()).select_from(AuditLog)
                .where(AuditLog.event == "competition.register")) == 1
            assert await db.scalar(select(func.count()).select_from(AuditLog)
                .where(AuditLog.event == "competition.unregister")) == 1

        # Reject the audit and prove neither registration nor unregistration
        # survives in this uniquely disposable PostgreSQL database.
        async with ctx.factory() as db:
            await db.execute(text(
                "ALTER TABLE audit_logs ADD CONSTRAINT block_registration "
                "CHECK (event <> 'competition.register') NOT VALID"
            ))
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            failed_register = await client.post(
                f"/api/v1/competitions/{rollback_id}/register"
            )
            assert failed_register.status_code == 503
        async with ctx.factory() as db:
            assert await db.scalar(select(func.count()).select_from(CompetitionParticipant)
                .where(CompetitionParticipant.competition_id == rollback_id)) == 0
            await db.execute(text("ALTER TABLE audit_logs DROP CONSTRAINT block_registration"))
            db.add(CompetitionParticipant(competition_id=rollback_id, user_id=student_id))
            await db.commit()
            await db.execute(text(
                "ALTER TABLE audit_logs ADD CONSTRAINT block_unregistration "
                "CHECK (event <> 'competition.unregister') NOT VALID"
            ))
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            failed_unregister = await client.post(
                f"/api/v1/competitions/{rollback_id}/unregister"
            )
            assert failed_unregister.status_code == 503
        async with ctx.factory() as db:
            assert await db.scalar(select(func.count()).select_from(CompetitionParticipant)
                .where(CompetitionParticipant.competition_id == rollback_id)) == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


async def test_rust_competition_team_writes_are_atomic_and_api_compatible(
    live_rust_database, monkeypatch
):
    ctx = live_rust_database
    student_id, teammate_id, _, _, _ = ctx.seeded
    settings = SimpleNamespace(
        rust_core_url=ctx.rust_url, rust_core_shared_token=ctx.token,
    )
    monkeypatch.setattr(rust_engine, "get_settings", lambda: settings)
    monkeypatch.setattr(authorization, "get_settings", lambda: settings)
    monkeypatch.setattr(competitions, "get_settings", lambda: settings)

    async def get_test_db():
        async with ctx.factory() as db:
            yield db

    current = [CurrentUser(
        id=student_id, keycloak_sub="team-test", roles=["student"],
    )]
    app.dependency_overrides[get_db] = get_test_db
    app.dependency_overrides[get_current_user] = lambda: current[0]
    async with ctx.factory() as db:
        active = Competition(
            slug="teams-open", title="Team-enabled CTF", status="registration",
            allow_teams=True, max_team_size=2, created_by=student_id,
        )
        closed = Competition(
            slug="teams-closed", title="Closed CTF", status="draft",
            allow_teams=True, created_by=student_id,
        )
        disabled = Competition(
            slug="teams-disabled", title="Solo CTF", status="registration",
            allow_teams=False, created_by=student_id,
        )
        rollback = Competition(
            slug="teams-rollback", title="Audit rollback CTF",
            status="scheduled", allow_teams=True, created_by=student_id,
        )
        db.add_all([active, closed, disabled, rollback])
        await db.flush()
        db.add_all([
            CompetitionParticipant(competition_id=active.id, user_id=student_id),
            CompetitionParticipant(competition_id=active.id, user_id=teammate_id),
            CompetitionParticipant(competition_id=rollback.id, user_id=student_id),
            CompetitionParticipant(competition_id=rollback.id, user_id=teammate_id),
        ])
        await db.commit()
        active_id, closed_id, disabled_id, rollback_id = (
            active.id, closed.id, disabled.id, rollback.id,
        )
    create_internal = f"{ctx.rust_url}/v1/competitions/teams/create"
    join_internal = f"{ctx.rust_url}/v1/competitions/teams/join"
    request_data = {
        "competition_id": str(active_id), "actor_id": str(student_id),
        "roles": ["student"], "ip_address": "127.0.0.1",
        "name": "Blue Team", "team_id": None,
    }
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            created = await client.post(
                f"/api/v1/competitions/{active_id}/teams",
                json={"name": " Blue Team "},
            )
            assert created.status_code == 200, created.text
            assert created.json()["team_count"] == 1
            second_team = await client.post(
                f"/api/v1/competitions/{active_id}/teams",
                json={"name": "Duplicate captain"},
            )
            assert second_team.status_code == 409
            assert second_team.json()["detail"] == (
                "You are already on a team in this competition."
            )
            closed_response = await client.post(
                f"/api/v1/competitions/{closed_id}/teams",
                json={"name": "Locked team"},
            )
            assert closed_response.status_code == 409
            disabled_response = await client.post(
                f"/api/v1/competitions/{disabled_id}/teams",
                json={"name": "Disabled team"},
            )
            assert disabled_response.status_code == 409

        async with ctx.factory() as db:
            team = await db.scalar(select(Team).where(
                Team.competition_id == active_id
            ))
            assert team is not None and team.name == "Blue Team"
            team_id = team.id
            captain = await db.scalar(select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == student_id,
            ))
            assert captain is not None and captain.role == "captain"
            participant = await db.scalar(select(CompetitionParticipant).where(
                CompetitionParticipant.competition_id == active_id,
                CompetitionParticipant.user_id == student_id,
            ))
            assert participant.team_id == team_id
            assert await db.scalar(select(func.count()).select_from(AuditLog)
                .where(AuditLog.event == "team.create")) == 1
        async with httpx.AsyncClient(timeout=2) as client:
            assert (await client.post(
                create_internal, json=request_data
            )).status_code == 401
            assert (await client.post(
                join_internal, json={**request_data, "name": None, "team_id": str(team_id)}
            )).status_code == 401
            assert (await client.post(
                create_internal,
                json={**request_data, "roles": ["competition_organizer"]},
                headers={"x-internal-token": ctx.token},
            )).status_code == 403
            assert (await client.post(
                join_internal,
                json={
                    **request_data, "name": None, "team_id": str(team_id),
                    "roles": ["competition_organizer"],
                },
                headers={"x-internal-token": ctx.token},
            )).status_code == 403
            assert (await client.post(
                create_internal, json={**request_data, "name": "  "},
                headers={"x-internal-token": ctx.token},
            )).status_code == 400
            assert (await client.post(
                join_internal, json={**request_data, "team_id": "invalid", "name": None},
                headers={"x-internal-token": ctx.token},
            )).status_code == 400

        current[0] = CurrentUser(
            id=teammate_id, keycloak_sub="team-test-2", roles=["student"],
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            joined = await client.post(
                f"/api/v1/competitions/{active_id}/teams/{team_id}/join",
            )
            assert joined.status_code == 200, joined.text
            assert joined.json()["team_count"] == 1
            again = await client.post(
                f"/api/v1/competitions/{active_id}/teams/{team_id}/join",
            )
            assert again.status_code == 409
            assert again.json()["detail"] == (
                "You are already on a team in this competition."
            )
            different_event = await client.post(
                f"/api/v1/competitions/{rollback_id}/teams/{team_id}/join",
            )
            assert different_event.status_code == 404
            assert different_event.json()["detail"] == "Team not found"
        async with ctx.factory() as db:
            member = await db.scalar(select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == teammate_id,
            ))
            assert member is not None and member.role == "member"
            participant = await db.scalar(select(CompetitionParticipant).where(
                CompetitionParticipant.competition_id == active_id,
                CompetitionParticipant.user_id == teammate_id,
            ))
            assert participant.team_id == team_id
            assert await db.scalar(select(func.count()).select_from(AuditLog)
                .where(AuditLog.event == "team.join")) == 1

        async with ctx.factory() as db:
            third = User(
                keycloak_sub=f"team-unregistered-{uuid.uuid4().hex}",
                display_name="Third teammate",
            )
            db.add(third)
            await db.commit()
            third_id = third.id
        current[0] = CurrentUser(
            id=third_id, keycloak_sub="team-test-3", roles=["student"],
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            not_registered = await client.post(
                f"/api/v1/competitions/{active_id}/teams/{team_id}/join",
            )
            assert not_registered.status_code == 409
            assert "Register for the competition" in not_registered.json()["detail"]
        async with ctx.factory() as db:
            db.add(CompetitionParticipant(
                competition_id=active_id, user_id=third_id,
            ))
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            full = await client.post(
                f"/api/v1/competitions/{active_id}/teams/{team_id}/join",
            )
            assert full.status_code == 409
            assert full.json()["detail"] == "Team is full (max 2)."

        # A disposable NOLOGIN role proves the SQL needs only column-scoped
        # privileges from security-core-role.sql.
        probe = f"cyberlab_teams_probe_{uuid.uuid4().hex[:10]}"
        async with ctx.factory() as db:
            try:
                await db.execute(text(f'CREATE ROLE "{probe}" NOLOGIN'))
                await db.execute(text(f'GRANT USAGE ON SCHEMA public TO "{probe}"'))
                for statement in (
                    "SELECT (id, slug, status, allow_teams, max_team_size) ON competitions",
                    "UPDATE (title) ON competitions",
                    "SELECT (id, competition_id, user_id, team_id) ON competition_participants",
                    "UPDATE (team_id) ON competition_participants",
                    "SELECT (id, competition_id, name) ON teams",
                    "INSERT (id, competition_id, name, created_by) ON teams",
                    "SELECT (team_id, user_id) ON team_members",
                    "INSERT (id, team_id, user_id, role) ON team_members",
                    "INSERT (id, event, user_id, target_id, ip_address, details) ON audit_logs",
                ):
                    await db.execute(text(f'GRANT {statement} TO "{probe}"'))
                await db.execute(text(f'SET LOCAL ROLE "{probe}"'))
                await db.execute(text(
                    "SELECT slug, status, allow_teams, max_team_size FROM competitions "
                    "WHERE id=:cid FOR UPDATE"
                ), {"cid": rollback_id})
                await db.execute(text(
                    "SELECT team_id::text FROM competition_participants "
                    "WHERE competition_id=:cid AND user_id=:uid FOR UPDATE"
                ), {"cid": rollback_id, "uid": student_id})
                probe_team = await db.scalar(text(
                    "INSERT INTO teams (id, competition_id, name, created_by) "
                    "VALUES (gen_random_uuid(), :cid, 'Probe Team', :uid) RETURNING id::text"
                ), {"cid": rollback_id, "uid": student_id})
                assert probe_team is not None
                await db.execute(text(
                    "INSERT INTO team_members (id, team_id, user_id, role) "
                    "VALUES (gen_random_uuid(), CAST(:tid AS uuid), :uid, 'captain')"
                ), {"tid": probe_team, "uid": student_id})
                await db.execute(text(
                    "UPDATE competition_participants SET team_id=CAST(:tid AS uuid) "
                    "WHERE competition_id=:cid AND user_id=:uid"
                ), {"tid": probe_team, "cid": rollback_id, "uid": student_id})
                assert await db.scalar(text(
                    "SELECT COUNT(*) FROM team_members WHERE team_id=CAST(:tid AS uuid)"
                ), {"tid": probe_team}) == 1
                await db.execute(text(
                    "INSERT INTO audit_logs "
                    "(id, event, user_id, target_id, details) "
                    "VALUES (gen_random_uuid(), 'team.create', :uid, 'Probe Team', "
                    """CAST('{"competition":"teams-rollback"}' AS jsonb))"""
                ), {"uid": student_id})
            finally:
                await db.rollback()

        # Force audit failure and assert all three team mutations roll back.
        current[0] = CurrentUser(
            id=student_id, keycloak_sub="team-test", roles=["student"],
        )
        async with ctx.factory() as db:
            await db.execute(text(
                "ALTER TABLE audit_logs ADD CONSTRAINT block_team_create "
                "CHECK (event <> 'team.create') NOT VALID"
            ))
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            failed_create = await client.post(
                f"/api/v1/competitions/{rollback_id}/teams",
                json={"name": "Must rollback"},
            )
            assert failed_create.status_code == 503
        async with ctx.factory() as db:
            assert await db.scalar(select(func.count()).select_from(Team)
                .where(Team.competition_id == rollback_id)) == 0
            member = await db.scalar(select(CompetitionParticipant).where(
                CompetitionParticipant.competition_id == rollback_id,
                CompetitionParticipant.user_id == student_id,
            ))
            assert member.team_id is None
            await db.execute(text("ALTER TABLE audit_logs DROP CONSTRAINT block_team_create"))
            precreated = Team(
                competition_id=rollback_id, name="Join rollback", created_by=teammate_id,
            )
            db.add(precreated)
            await db.flush()
            db.add(TeamMember(
                team_id=precreated.id, user_id=teammate_id, role="captain",
            ))
            other = await db.scalar(select(CompetitionParticipant).where(
                CompetitionParticipant.competition_id == rollback_id,
                CompetitionParticipant.user_id == teammate_id,
            ))
            other.team_id = precreated.id
            await db.commit()
            precreated_id = precreated.id
            await db.execute(text(
                "ALTER TABLE audit_logs ADD CONSTRAINT block_team_join "
                "CHECK (event <> 'team.join') NOT VALID"
            ))
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            failed_join = await client.post(
                f"/api/v1/competitions/{rollback_id}/teams/{precreated_id}/join",
            )
            assert failed_join.status_code == 503
        async with ctx.factory() as db:
            assert await db.scalar(select(func.count()).select_from(TeamMember)
                .where(TeamMember.team_id == precreated_id)) == 1
            participant = await db.scalar(select(CompetitionParticipant).where(
                CompetitionParticipant.competition_id == rollback_id,
                CompetitionParticipant.user_id == student_id,
            ))
            assert participant.team_id is None
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


async def test_rust_competition_freeze_is_atomic_and_api_compatible(
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
        id=organizer_id, keycloak_sub="freeze-faculty", roles=["faculty"],
    )
    async with ctx.factory() as db:
        finished = Competition(
            slug="freeze-finished", title="Finished competition",
            status="finished", created_by=organizer_id,
        )
        rollback = Competition(
            slug="freeze-rollback", title="Freeze audit rollback",
            status="draft", created_by=organizer_id,
        )
        db.add_all([finished, rollback])
        await db.commit()
        finished_id, rollback_id = finished.id, rollback.id
    internal = f"{ctx.rust_url}/v1/competitions/freeze"
    request_data = {
        "competition_id": str(finished_id),
        "actor_id": str(organizer_id), "roles": ["faculty"],
        "ip_address": "127.0.0.1", "frozen": True,
    }
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            first = await client.post(
                f"/api/v1/competitions/{finished_id}/freeze",
            )
            assert first.status_code == 200, first.text
            assert first.json()["status"] == "finished"
            assert first.json()["freeze_leaderboard"] is True
            assert first.json()["frozen_at"] is not None
            repeated = await client.post(
                f"/api/v1/competitions/{finished_id}/freeze",
            )
            assert repeated.status_code == 200, repeated.text
            assert repeated.json()["freeze_leaderboard"] is True
            unfrozen = await client.post(
                f"/api/v1/competitions/{finished_id}/unfreeze",
            )
            assert unfrozen.status_code == 200, unfrozen.text
            assert unfrozen.json()["freeze_leaderboard"] is False
            assert unfrozen.json()["frozen_at"] is None
        async with ctx.factory() as db:
            saved = await db.get(Competition, finished_id)
            assert saved.freeze_leaderboard is False
            assert saved.frozen_at is None
            audits = (await db.scalars(select(AuditLog).where(
                AuditLog.event.in_(["competition.freeze", "competition.unfreeze"]),
            ))).all()
            assert len(audits) == 3
            assert sum(a.event == "competition.freeze" for a in audits) == 2
            assert all(a.target_id == "freeze-finished" for a in audits)

        async with httpx.AsyncClient(timeout=2) as client:
            missing = await client.post(internal, json=request_data)
            assert missing.status_code == 401
            forbidden = await client.post(
                internal, json={**request_data, "roles": ["student"]},
                headers={"x-internal-token": ctx.token},
            )
            assert forbidden.status_code == 403
            invalid = await client.post(
                internal, json={**request_data, "actor_id": "not-a-uuid"},
                headers={"x-internal-token": ctx.token},
            )
            assert invalid.status_code == 400
            absent = await client.post(
                internal,
                json={**request_data, "competition_id": str(uuid.uuid4())},
                headers={"x-internal-token": ctx.token},
            )
            assert absent.status_code == 200
            assert absent.json()["outcome"] == "not_found"

        # Exercise the exact write operations with a disposable, column-scoped
        # NOLOGIN role; rolling back also removes the temporary PostgreSQL role.
        probe = f"cyberlab_freeze_probe_{uuid.uuid4().hex[:10]}"
        async with ctx.factory() as db:
            try:
                await db.execute(text(f'CREATE ROLE "{probe}" NOLOGIN'))
                await db.execute(text(f'GRANT USAGE ON SCHEMA public TO "{probe}"'))
                await db.execute(text(
                    f'GRANT SELECT (id, slug) ON competitions TO "{probe}"'
                ))
                await db.execute(text(
                    'GRANT UPDATE (freeze_leaderboard, frozen_at, updated_at) '
                    f'ON competitions TO "{probe}"'
                ))
                await db.execute(text(
                    'GRANT INSERT (id, event, user_id, target_id, ip_address) '
                    f'ON audit_logs TO "{probe}"'
                ))
                await db.execute(text(f'SET LOCAL ROLE "{probe}"'))
                slug = await db.scalar(text(
                    "SELECT slug FROM competitions WHERE id=:cid FOR UPDATE"
                ), {"cid": rollback_id})
                assert slug == "freeze-rollback"
                await db.execute(text(
                    "UPDATE competitions SET freeze_leaderboard=true, "
                    "frozen_at=now(), updated_at=now() WHERE id=:cid"
                ), {"cid": rollback_id})
                await db.execute(text(
                    "INSERT INTO audit_logs (id, event, user_id, target_id) "
                    "VALUES (gen_random_uuid(), 'competition.freeze', :uid, :target)"
                ), {"uid": organizer_id, "target": slug})
            finally:
                await db.rollback()

        # A failed audit must revert both the boolean and timestamp updates.
        async with ctx.factory() as db:
            await db.execute(text(
                "ALTER TABLE audit_logs ADD CONSTRAINT block_freeze "
                "CHECK (event <> 'competition.freeze') NOT VALID"
            ))
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            failure = await client.post(
                f"/api/v1/competitions/{rollback_id}/freeze",
            )
            assert failure.status_code == 503
        async with ctx.factory() as db:
            unchanged = await db.get(Competition, rollback_id)
            assert unchanged.freeze_leaderboard is False
            assert unchanged.frozen_at is None
            await db.execute(text("ALTER TABLE audit_logs DROP CONSTRAINT block_freeze"))
            unchanged.freeze_leaderboard = True
            unchanged.frozen_at = datetime.now(UTC)
            await db.commit()
            await db.execute(text(
                "ALTER TABLE audit_logs ADD CONSTRAINT block_unfreeze "
                "CHECK (event <> 'competition.unfreeze') NOT VALID"
            ))
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            failed_unfreeze = await client.post(
                f"/api/v1/competitions/{rollback_id}/unfreeze",
            )
            assert failed_unfreeze.status_code == 503
        async with ctx.factory() as db:
            unchanged = await db.get(Competition, rollback_id)
            assert unchanged.freeze_leaderboard is True
            assert unchanged.frozen_at is not None
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


async def test_rust_manual_competition_transitions_are_atomic_and_api_compatible(
    live_rust_database, monkeypatch
):
    ctx = live_rust_database
    organizer_id, other_id, _, _, _ = ctx.seeded
    settings = SimpleNamespace(
        rust_core_url=ctx.rust_url, rust_core_shared_token=ctx.token,
    )
    monkeypatch.setattr(rust_engine, "get_settings", lambda: settings)
    monkeypatch.setattr(authorization, "get_settings", lambda: settings)
    monkeypatch.setattr(competitions, "get_settings", lambda: settings)
    badge_hook = AsyncMock()
    monkeypatch.setattr(
        "app.services.badges.grant_eligible_badges", badge_hook,
    )

    async def get_test_db():
        async with ctx.factory() as db:
            yield db

    app.dependency_overrides[get_db] = get_test_db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=organizer_id, keycloak_sub="transition-faculty", roles=["faculty"],
    )
    now = datetime.now(UTC)
    async with ctx.factory() as db:
        draft = Competition(
            slug="manual-draft", title="Open registration",
            status="draft", created_by=organizer_id,
        )
        scheduled = Competition(
            slug="manual-scheduled", title="Start competition",
            status="scheduled", start_at=now - timedelta(minutes=2),
            end_at=now + timedelta(hours=1), created_by=organizer_id,
        )
        future = Competition(
            slug="manual-future", title="Too early",
            status="scheduled", start_at=now + timedelta(hours=1),
            end_at=now + timedelta(hours=2), created_by=organizer_id,
        )
        live = Competition(
            slug="manual-live", title="Finish competition",
            status="live", created_by=organizer_id,
        )
        archived = Competition(
            slug="manual-archivable", title="Archive competition",
            status="finished", created_by=organizer_id,
        )
        incomplete = Competition(
            slug="manual-incomplete", title="Schedule missing",
            status="registration", created_by=organizer_id,
        )
        ready = Competition(
            slug="manual-ready", title="Schedule complete",
            status="registration", start_at=now + timedelta(hours=1),
            end_at=now + timedelta(hours=2), created_by=organizer_id,
        )
        rollback = Competition(
            slug="manual-rollback", title="Audit failure",
            status="draft", created_by=organizer_id,
        )
        racing = Competition(
            slug="manual-racing", title="Concurrent transition",
            status="draft", created_by=organizer_id,
        )
        db.add_all([
            draft, scheduled, future, live, archived, incomplete, ready, rollback, racing,
        ])
        await db.flush()
        db.add_all([
            CompetitionParticipant(competition_id=live.id, user_id=organizer_id),
            CompetitionParticipant(competition_id=live.id, user_id=other_id),
        ])
        await db.commit()
        draft_id, scheduled_id, future_id, live_id = (
            draft.id, scheduled.id, future.id, live.id,
        )
        archive_id, incomplete_id, rollback_id, racing_id = (
            archived.id, incomplete.id, rollback.id, racing.id,
        )
        ready_id = ready.id
    internal = f"{ctx.rust_url}/v1/competitions/transition/persist"
    request_data = {
        "competition_id": str(draft_id), "action": "start_registration",
        "actor_id": str(organizer_id), "roles": ["faculty"],
        "ip_address": "127.0.0.1",
    }
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            async def change(competition_id, action):
                return await client.post(
                    f"/api/v1/competitions/{competition_id}/transition",
                    json={"action": action},
                )

            opened = await change(draft_id, "start_registration")
            assert opened.status_code == 200, opened.text
            assert opened.json()["status"] == "registration"
            missing = await change(incomplete_id, "schedule")
            assert missing.status_code == 400
            assert missing.json()["detail"] == (
                "Set start_at and end_at before scheduling."
            )
            scheduled_response = await change(ready_id, "schedule")
            assert scheduled_response.status_code == 200, scheduled_response.text
            assert scheduled_response.json()["status"] == "scheduled"
            too_early = await change(future_id, "start")
            assert too_early.status_code == 409
            assert too_early.json()["detail"] == (
                "Competition cannot start before its scheduled start time."
            )
            started = await change(scheduled_id, "start")
            assert started.status_code == 200, started.text
            assert started.json()["status"] == "live"
            finished = await change(live_id, "finish")
            assert finished.status_code == 200, finished.text
            assert finished.json()["status"] == "finished"
            assert badge_hook.await_count == 2
            archived_response = await change(archive_id, "archive")
            assert archived_response.status_code == 200, archived_response.text
            assert archived_response.json()["status"] == "archived"
            incorrect = await change(draft_id, "start")
            assert incorrect.status_code == 409
            assert incorrect.json()["detail"] == (
                "Cannot start: competition is 'registration', expected 'scheduled'."
            )

            # Competing requests must serialize on the competition row; only
            # one can perform the draft -> registration transition and audit.
            first, second = await asyncio.gather(
                change(racing_id, "start_registration"),
                change(racing_id, "start_registration"),
            )
            assert sorted([first.status_code, second.status_code]) == [200, 409]
        async with ctx.factory() as db:
            transition_audits = (await db.scalars(select(AuditLog).where(
                AuditLog.event == "competition.transition",
            ))).all()
            assert len(transition_audits) == 6
            assert {
                audit.details["action"] for audit in transition_audits
            } == {"start_registration", "schedule", "start", "finish", "archive"}
            finish_audit = next(
                audit for audit in transition_audits
                if audit.target_id == "manual-live"
            )
            assert finish_audit.details == {
                "action": "finish", "from": "live", "to": "finished",
            }
            assert await db.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.event == "competition.badges_reconciled",
                AuditLog.target_id == "manual-live",
            )) == 1

        async with httpx.AsyncClient(timeout=2) as client:
            assert (await client.post(
                internal, json=request_data,
            )).status_code == 401
            assert (await client.post(
                internal, json={**request_data, "roles": ["student"]},
                headers={"x-internal-token": ctx.token},
            )).status_code == 403
            assert (await client.post(
                internal, json={**request_data, "actor_id": "invalid"},
                headers={"x-internal-token": ctx.token},
            )).status_code == 400
            bypass = await client.post(
                internal, json={**request_data, "action": "auto"},
                headers={"x-internal-token": ctx.token},
            )
            assert bypass.status_code == 200
            assert bypass.json()["outcome"] == "unknown_action"
            absent = await client.post(
                internal,
                json={**request_data, "competition_id": str(uuid.uuid4())},
                headers={"x-internal-token": ctx.token},
            )
            assert absent.status_code == 200
            assert absent.json()["outcome"] == "not_found"

        # Exercise the selected SQL operations under a temporary minimal role.
        probe = f"cyberlab_transition_probe_{uuid.uuid4().hex[:10]}"
        async with ctx.factory() as db:
            try:
                await db.execute(text(f'CREATE ROLE "{probe}" NOLOGIN'))
                await db.execute(text(f'GRANT USAGE ON SCHEMA public TO "{probe}"'))
                await db.execute(text(
                    'GRANT SELECT (id, slug, status, start_at, end_at) '
                    f'ON competitions TO "{probe}"'
                ))
                await db.execute(text(
                    'GRANT UPDATE (status, updated_at) '
                    f'ON competitions TO "{probe}"'
                ))
                await db.execute(text(
                    'GRANT INSERT (id, event, user_id, target_id, ip_address, details) '
                    f'ON audit_logs TO "{probe}"'
                ))
                await db.execute(text(f'SET LOCAL ROLE "{probe}"'))
                row = (await db.execute(text(
                    "SELECT slug, status, "
                    "floor(extract(epoch FROM start_at) * 1000)::bigint, "
                    "floor(extract(epoch FROM end_at) * 1000)::bigint, "
                    "floor(extract(epoch FROM now()) * 1000)::bigint "
                    "FROM competitions WHERE id=:cid FOR UPDATE"
                ), {"cid": rollback_id})).one()
                assert row[0] == "manual-rollback" and row[1] == "draft"
                await db.execute(text(
                    "UPDATE competitions SET status='registration', updated_at=now() "
                    "WHERE id=:cid"
                ), {"cid": rollback_id})
                await db.execute(text(
                    "INSERT INTO audit_logs "
                    "(id, event, user_id, target_id, details) "
                    "VALUES (gen_random_uuid(), 'competition.transition', "
                    ":uid, 'manual-rollback', CAST(:details AS jsonb))"
                ), {
                    "uid": organizer_id,
                    "details": (
                        '{"action":"start_registration","from":"draft",'
                        '"to":"registration"}'
                    ),
                })
            finally:
                await db.rollback()

        async with ctx.factory() as db:
            await db.execute(text(
                "ALTER TABLE audit_logs ADD CONSTRAINT block_manual_transition "
                "CHECK (event <> 'competition.transition') NOT VALID"
            ))
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            failed = await client.post(
                f"/api/v1/competitions/{rollback_id}/transition",
                json={"action": "start_registration"},
            )
            assert failed.status_code == 503
        async with ctx.factory() as db:
            assert (await db.get(Competition, rollback_id)).status == "draft"
            assert await db.scalar(select(func.count()).select_from(AuditLog)
                .where(AuditLog.target_id == "manual-rollback")) == 0
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


async def test_concurrent_competition_finish_badge_claims(
    live_rust_database, monkeypatch
):
    """Only one worker may reconcile a given finish event at a time."""
    ctx = live_rust_database
    organizer_id, _, _, _, _ = ctx.seeded
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def slow_badge_grant(db, user_id, request=None):
        calls.append(user_id)
        entered.set()
        await release.wait()

    monkeypatch.setattr(
        "app.services.badges.grant_eligible_badges", slow_badge_grant
    )
    async with ctx.factory() as db:
        comp = Competition(
            slug="badge-claim-race", title="Concurrent badge claim",
            status="finished", created_by=organizer_id,
        )
        db.add(comp)
        await db.flush()
        db.add_all([
            CompetitionParticipant(competition_id=comp.id, user_id=organizer_id),
            AuditLog(
                event="competition.transition", target_id=comp.slug,
                details={"action": "finish", "from": "live", "to": "finished"},
            ),
        ])
        await db.commit()

    async def reconcile():
        async with ctx.factory() as db:
            await competitions._reconcile_finished_badge_events(
                db, target_slug="badge-claim-race"
            )

    first = asyncio.create_task(reconcile())
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        # The first grant remains in progress while the second worker tries.
        await asyncio.wait_for(reconcile(), timeout=5)
        assert calls == [organizer_id]
    finally:
        release.set()
        await first

    async with ctx.factory() as db:
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "competition.badges_reconciled",
            AuditLog.target_id == "badge-claim-race",
        )) == 1
    await reconcile()
    assert calls == [organizer_id]


async def test_rust_auto_transitions_audit_and_retry_badge_followups(
    live_rust_database, monkeypatch
):
    ctx = live_rust_database
    organizer_id, other_id, _, _, _ = ctx.seeded
    settings = SimpleNamespace(
        rust_core_url=ctx.rust_url, rust_core_shared_token=ctx.token,
    )
    monkeypatch.setattr(rust_engine, "get_settings", lambda: settings)
    monkeypatch.setattr(competitions, "get_settings", lambda: settings)
    badge_hook = AsyncMock()
    monkeypatch.setattr("app.services.badges.grant_eligible_badges", badge_hook)
    now = datetime.now(UTC)
    async with ctx.factory() as db:
        opening = Competition(
            slug="auto-opening", title="Starting now", status="scheduled",
            start_at=now - timedelta(minutes=1),
            end_at=now + timedelta(hours=1), created_by=organizer_id,
        )
        ending = Competition(
            slug="auto-ending", title="Ending now", status="live",
            end_at=now - timedelta(minutes=1), created_by=organizer_id,
        )
        overdue = Competition(
            slug="auto-overdue", title="Start and finish", status="scheduled",
            start_at=now - timedelta(hours=2),
            end_at=now - timedelta(hours=1), created_by=organizer_id,
        )
        future = Competition(
            slug="auto-future", title="Not yet due", status="scheduled",
            start_at=now + timedelta(hours=1),
            end_at=now + timedelta(hours=2), created_by=organizer_id,
        )
        manual_done = Competition(
            slug="manual-finish-pending", title="Manual retry",
            status="finished", created_by=organizer_id,
        )
        db.add_all([opening, ending, overdue, future, manual_done])
        await db.flush()
        db.add_all([
            CompetitionParticipant(competition_id=ending.id, user_id=organizer_id),
            CompetitionParticipant(competition_id=ending.id, user_id=other_id),
            CompetitionParticipant(competition_id=overdue.id, user_id=organizer_id),
            CompetitionParticipant(competition_id=manual_done.id, user_id=other_id),
            AuditLog(
                event="competition.transition",
                target_id="manual-finish-pending",
                user_id=organizer_id,
                details={"action": "finish", "from": "live", "to": "finished"},
            ),
        ])
        await db.commit()
        opening_id, ending_id, overdue_id, future_id = (
            opening.id, ending.id, overdue.id, future.id,
        )
    internal = f"{ctx.rust_url}/v1/competitions/transition/auto"

    async with httpx.AsyncClient(timeout=2) as client:
        no_token = await client.post(internal, json={})
        assert no_token.status_code == 401
    async with ctx.factory() as db:
        changed = await competitions.auto_transition_competitions(db)
        assert changed == 4
        assert badge_hook.await_count == 4
    async with ctx.factory() as db:
        assert (await db.get(Competition, opening_id)).status == "live"
        assert (await db.get(Competition, ending_id)).status == "finished"
        assert (await db.get(Competition, overdue_id)).status == "finished"
        assert (await db.get(Competition, future_id)).status == "scheduled"
        audits = (await db.scalars(select(AuditLog).where(
            AuditLog.event == "competition.auto_transition"
        ))).all()
        assert len(audits) == 4
        assert all(a.user_id is None for a in audits)
        assert {
            (a.target_id, a.details["from"], a.details["to"]) for a in audits
        } == {
            ("auto-opening", "scheduled", "live"),
            ("auto-ending", "live", "finished"),
            ("auto-overdue", "scheduled", "live"),
            ("auto-overdue", "live", "finished"),
        }
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "competition.badges_reconciled"
        )) == 3
    async with ctx.factory() as db:
        assert await competitions.auto_transition_competitions(db) == 0
        assert badge_hook.await_count == 4

    # Two concurrent Rust sweeps must transition a due row only once.
    async with ctx.factory() as db:
        racing = Competition(
            slug="auto-racing", title="Concurrent scheduler",
            status="scheduled", start_at=now - timedelta(minutes=1),
            end_at=now + timedelta(hours=1), created_by=organizer_id,
        )
        db.add(racing)
        await db.commit()
        racing_id = racing.id
    async with httpx.AsyncClient(timeout=5) as client:
        async def sweep():
            return await client.post(
                internal, json={},
                headers={"x-internal-token": ctx.token},
            )

        first, second = await asyncio.gather(sweep(), sweep())
        assert first.status_code == second.status_code == 200
        assert first.json()["changed"] + second.json()["changed"] == 1
    async with ctx.factory() as db:
        assert (await db.get(Competition, racing_id)).status == "live"
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "competition.auto_transition",
            AuditLog.target_id == "auto-racing",
        )) == 1

    # The Rust transition commits before Python awards badges. A failing
    # callback must leave an unacknowledged finish event for the next sweep.
    async with ctx.factory() as db:
        retry_comp = Competition(
            slug="auto-retry", title="Retry badges", status="live",
            end_at=now - timedelta(minutes=1), created_by=organizer_id,
        )
        db.add(retry_comp)
        await db.flush()
        db.add(CompetitionParticipant(
            competition_id=retry_comp.id, user_id=organizer_id,
        ))
        await db.commit()
        retry_id = retry_comp.id
    badge_hook.side_effect = RuntimeError("simulated badge delivery failure")
    async with ctx.factory() as db:
        with pytest.raises(RuntimeError, match="simulated badge"):
            await competitions.auto_transition_competitions(db)
        await db.rollback()
    async with ctx.factory() as db:
        assert (await db.get(Competition, retry_id)).status == "finished"
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "competition.auto_transition",
            AuditLog.target_id == "auto-retry",
        )) == 1
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "competition.badges_reconciled"
        )) == 3
    badge_hook.side_effect = None
    before_retry = badge_hook.await_count
    async with ctx.factory() as db:
        assert await competitions.auto_transition_competitions(db) == 0
    assert badge_hook.await_count == before_retry + 1
    async with ctx.factory() as db:
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "competition.badges_reconciled"
        )) == 4
        assert await competitions.auto_transition_competitions(db) == 0
        assert badge_hook.await_count == before_retry + 1

    # Verify selected SQL on a disposable NOLOGIN role without persisting
    # grants, including SKIP LOCKED and the audit column allowlist.
    async with ctx.factory() as db:
        probe_comp = Competition(
            slug="auto-probe", title="Restricted scheduler", status="scheduled",
            start_at=now - timedelta(hours=1), created_by=organizer_id,
        )
        db.add(probe_comp)
        await db.commit()
        probe_id = probe_comp.id
    probe = f"cyberlab_auto_probe_{uuid.uuid4().hex[:10]}"
    async with ctx.factory() as db:
        try:
            await db.execute(text(f'CREATE ROLE "{probe}" NOLOGIN'))
            await db.execute(text(f'GRANT USAGE ON SCHEMA public TO "{probe}"'))
            await db.execute(text(
                'GRANT SELECT (id, slug, status, start_at, end_at) '
                f'ON competitions TO "{probe}"'
            ))
            await db.execute(text(
                'GRANT UPDATE (status, updated_at) '
                f'ON competitions TO "{probe}"'
            ))
            await db.execute(text(
                'GRANT INSERT (id, event, target_id, details) '
                f'ON audit_logs TO "{probe}"'
            ))
            await db.execute(text(f'SET LOCAL ROLE "{probe}"'))
            rows = (await db.execute(text(
                "SELECT id::text, slug, status, "
                "floor(extract(epoch FROM start_at) * 1000)::bigint, "
                "floor(extract(epoch FROM end_at) * 1000)::bigint, "
                "floor(extract(epoch FROM now()) * 1000)::bigint "
                "FROM competitions WHERE status='scheduled' AND start_at<=now() "
                "ORDER BY id LIMIT 250 FOR UPDATE SKIP LOCKED"
            ))).all()
            assert any(row[0] == str(probe_id) for row in rows)
            await db.execute(text(
                "UPDATE competitions SET status='live', updated_at=now() "
                "WHERE id=:cid"
            ), {"cid": probe_id})
            await db.execute(text(
                "INSERT INTO audit_logs (id, event, target_id, details) "
                "VALUES (gen_random_uuid(), 'competition.auto_transition', "
                "'auto-probe', CAST(:details AS jsonb))"
            ), {"details": '{"action":"auto","from":"scheduled","to":"live"}'})
        finally:
            await db.rollback()

    # If an automatic audit cannot be inserted, no status change may survive.
    async with ctx.factory() as db:
        await db.execute(text(
            "ALTER TABLE audit_logs ADD CONSTRAINT block_auto_transition "
            "CHECK (event <> 'competition.auto_transition') NOT VALID"
        ))
        await db.commit()
    async with httpx.AsyncClient(timeout=5) as client:
        failed = await client.post(
            internal, json={},
            headers={"x-internal-token": ctx.token},
        )
        assert failed.status_code == 503
    async with ctx.factory() as db:
        assert (await db.get(Competition, probe_id)).status == "scheduled"
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "competition.auto_transition",
            AuditLog.target_id == "auto-probe",
        )) == 0


async def test_rust_lab_lease_extension_api_auth_concurrency_and_audit_rollback(
    live_rust_database, monkeypatch
):
    ctx = live_rust_database
    owner_id, other_id, challenge_id, _, _ = ctx.seeded
    settings = SimpleNamespace(
        rust_core_url=ctx.rust_url, rust_core_shared_token=ctx.token,
        lab_max_expiry_minutes=240,
    )
    from app.core import authorization
    from app.services import labs

    monkeypatch.setattr(rust_engine, "get_settings", lambda: settings)
    monkeypatch.setattr(authorization, "get_settings", lambda: settings)
    monkeypatch.setattr(labs, "get_settings", lambda: settings)
    now = datetime.now(UTC)
    async with ctx.factory() as db:
        running = LabInstance(
            user_id=owner_id, challenge_id=challenge_id, status="running",
            expires_at=now + timedelta(minutes=30),
        )
        racing = LabInstance(
            user_id=owner_id, challenge_id=challenge_id, status="running",
            expires_at=now + timedelta(minutes=15),
        )
        stopped = LabInstance(
            user_id=owner_id, challenge_id=challenge_id, status="stopped",
        )
        expired = LabInstance(
            user_id=owner_id, challenge_id=challenge_id, status="running",
            expires_at=now - timedelta(minutes=1),
        )
        rollback = LabInstance(
            user_id=owner_id, challenge_id=challenge_id, status="running",
            expires_at=now + timedelta(minutes=20),
        )
        admin_target = LabInstance(
            user_id=owner_id, challenge_id=challenge_id, status="running",
            expires_at=now + timedelta(minutes=20),
        )
        db.add_all([running, racing, stopped, expired, rollback, admin_target])
        await db.commit()
        running_id, racing_id, stopped_id = running.id, racing.id, stopped.id
        expired_id, rollback_id = expired.id, rollback.id
        admin_id = admin_target.id

    async def get_test_db():
        async with ctx.factory() as db:
            yield db

    app.dependency_overrides[get_db] = get_test_db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=owner_id, keycloak_sub="lease-test", roles=["student"],
        permissions=["lab.launch"],
    )
    internal = f"{ctx.rust_url}/v1/labs/extend"
    direct_payload = {
        "lab_id": str(racing_id), "actor_id": str(owner_id),
        "roles": ["student"], "ip_address": "127.0.0.1",
        "additional_minutes": 30, "max_expiry_minutes": 240,
    }
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            result = await client.put(
                f"/api/v1/labs/{running_id}/extend",
                json={"additional_minutes": 30},
            )
            assert result.status_code == 200, result.text
            assert result.json()["status"] == "running"
            updated_exp = datetime.fromisoformat(result.json()["expires_at"])
            assert abs((updated_exp - (now + timedelta(minutes=60))).total_seconds()) < 3
            for lab_id, expected_detail in [
                (stopped_id, "must be running"),
                (expired_id, "already expired"),
            ]:
                denied = await client.put(
                    f"/api/v1/labs/{lab_id}/extend", json={},
                )
                assert denied.status_code == 400, denied.text
                assert expected_detail in denied.json()["detail"]

        async with httpx.AsyncClient(timeout=5) as client:
            assert (await client.post(internal, json=direct_payload)).status_code == 401
            for invalid, expected_status in [
                ({"actor_id": str(other_id)}, 403),
                ({"roles": ["guest"]}, 403),
                ({"additional_minutes": 500}, 400),
                ({"max_expiry_minutes": 0}, 400),
            ]:
                result = await client.post(
                    internal, json={**direct_payload, **invalid},
                    headers={"x-internal-token": ctx.token},
                )
                assert result.status_code == expected_status, result.text

            admin_result = await client.post(
                internal,
                json={**direct_payload, "lab_id": str(admin_id),
                      "actor_id": str(other_id), "roles": ["sysadmin"]},
                headers={"x-internal-token": ctx.token},
            )
            assert admin_result.status_code == 200, admin_result.text
            assert admin_result.json()["outcome"] == "extended"

            async def extend_racing():
                return await client.post(
                    internal, json=direct_payload,
                    headers={"x-internal-token": ctx.token},
                )

            first, second = await asyncio.gather(extend_racing(), extend_racing())
            assert first.status_code == second.status_code == 200
            assert first.json()["outcome"] == second.json()["outcome"] == "extended"
        async with ctx.factory() as db:
            refreshed = await db.get(LabInstance, racing_id)
            assert abs((refreshed.expires_at.replace(tzinfo=UTC) - (
                now + timedelta(minutes=75)
            )).total_seconds()) < 3
            assert await db.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.event == "lab.extend",
                AuditLog.target_id == str(racing_id),
            )) == 2
            assert await db.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.event == "lab.extend",
                AuditLog.target_id == str(running_id),
            )) == 1

        # Check the specific SQL under a disposable restricted PostgreSQL role.
        probe = f"cyberlab_lease_probe_{uuid.uuid4().hex[:10]}"
        async with ctx.factory() as db:
            try:
                await db.execute(text(f'CREATE ROLE "{probe}" NOLOGIN'))
                await db.execute(text(f'GRANT USAGE ON SCHEMA public TO "{probe}"'))
                await db.execute(text(
                    'GRANT SELECT (id, user_id, status, expires_at, created_at) '
                    f'ON lab_instances TO "{probe}"'
                ))
                await db.execute(text(
                    'GRANT UPDATE (expires_at, updated_at) '
                    f'ON lab_instances TO "{probe}"'
                ))
                await db.execute(text(
                    'GRANT INSERT (id, event, user_id, target_id, ip_address) '
                    f'ON audit_logs TO "{probe}"'
                ))
                await db.execute(text(f'SET LOCAL ROLE "{probe}"'))
                row = (await db.execute(text(
                    'SELECT user_id::text, status, COALESCE(expires_at < now(), false) '
                    'FROM lab_instances WHERE id = :lab_id FOR UPDATE'
                ), {"lab_id": racing_id})).one()
                assert row[0] == str(owner_id) and row[1] == "running"
                await db.execute(text(
                    "UPDATE lab_instances SET expires_at = LEAST("
                    "COALESCE(expires_at, now()) + 30 * interval '1 minute', "
                    "COALESCE(created_at, now()) + 240 * interval '1 minute'), "
                    "updated_at = now() WHERE id = :lab_id"
                ), {"lab_id": racing_id})
                await db.execute(text(
                    "INSERT INTO audit_logs (id, event, user_id, target_id, ip_address) "
                    "VALUES (gen_random_uuid(), 'lab.extend', :uid, :lid, '127.0.0.1')"
                ), {"uid": owner_id, "lid": str(racing_id)})
            finally:
                await db.rollback()

        async with ctx.factory() as db:
            await db.execute(text(
                "ALTER TABLE audit_logs ADD CONSTRAINT block_lab_extend "
                "CHECK (event <> 'lab.extend') NOT VALID"
            ))
            await db.commit()
        async with httpx.AsyncClient(timeout=5) as client:
            failed = await client.post(
                internal, json={**direct_payload, "lab_id": str(rollback_id)},
                headers={"x-internal-token": ctx.token},
            )
            assert failed.status_code == 503
        async with ctx.factory() as db:
            unchanged = await db.get(LabInstance, rollback_id)
            assert abs((unchanged.expires_at.replace(tzinfo=UTC) - (
                now + timedelta(minutes=20)
            )).total_seconds()) < 3
            assert await db.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.event == "lab.extend",
                AuditLog.target_id == str(rollback_id),
            )) == 0
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
