import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import get_settings
from app.db.base import Base

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

import uuid
from collections.abc import AsyncIterator
import httpx
from app.api.deps import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.models import User

def _student(sub: str = "student-sub-test") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["student"],
        permissions=["challenge.view", "submission.create", "learning_path.view"],
    )

def _faculty(sub: str = "faculty-sub-test") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        keycloak_sub=sub,
        roles=["faculty"],
        permissions=["challenge.view", "challenge.edit", "learning_path.manage"],
    )

async def _ensure_user(factory, user: CurrentUser) -> None:
    async with factory() as db:
        if await db.get(User, user.id) is None:
            db.add(User(id=user.id, keycloak_sub=user.keycloak_sub, email=f"{user.keycloak_sub}@cyberlab.test", display_name="Test User"))
            await db.commit()

@pytest.fixture
async def student_client(test_db):
    user = _student()
    await _ensure_user(test_db, user)
    
    async def _db() -> AsyncIterator[AsyncSession]:
        async with test_db() as session:
            yield session
            
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    yield client, user
    app.dependency_overrides.clear()
