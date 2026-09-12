# Test fixtures.

import pytest


@pytest.fixture
def client():
    """Placeholder; replaced by a real TestClient in Stage 2+."""
    from app.main import app

    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"