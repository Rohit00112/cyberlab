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
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import CurrentUser, get_current_user
from app.core import authorization, rust_engine
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Challenge, Submission, User  # noqa: F401 (registers tables)
from app.services import challenges, submissions

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
                points=150, status="published",
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
                    response = await client.get(f"{rust_url}/health")
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.1)
            else:
                pytest.fail("Rust service health endpoint never became ready")

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
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
