from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core.permissions import has_permission


def test_has_permission():
    assert has_permission(["sysadmin"], "anything.at.all") is True
    assert has_permission(["faculty"], "challenge.edit") is True
    assert has_permission(["faculty"], "submission.create") is False
    assert has_permission(["student"], "submission.create") is True
    assert has_permission(["student"], "challenge.edit") is False
    assert has_permission(["lab_admin"], "audit.view") is True
    assert has_permission([], "challenge.view") is False


def _make_app(user: CurrentUser) -> TestClient:
    app = FastAPI()

    def fake_current_user():
        return user

    app.dependency_overrides[get_current_user] = fake_current_user

    @app.get("/admin-challenge")
    async def admin_challenge(
        _=Depends(require_permission("challenge.edit")),  # noqa: B008
    ):
        return {"ok": True}

    return TestClient(app)


def test_require_permission_sysadmin_allowed():
    user = CurrentUser(
        id="00000000-0000-0000-0000-000000000000",
        keycloak_sub="s1",
        roles=["sysadmin"],
        permissions=["*"],
    )
    client = _make_app(user)
    assert client.get("/admin-challenge").status_code == 200


def test_require_permission_faculty_allowed():
    user = CurrentUser(
        id="00000000-0000-0000-0000-000000000001",
        keycloak_sub="f1",
        roles=["faculty"],
        permissions=["challenge.edit"],
    )
    client = _make_app(user)
    assert client.get("/admin-challenge").status_code == 200


def test_require_permission_student_forbidden():
    user = CurrentUser(
        id="00000000-0000-0000-0000-000000000002",
        keycloak_sub="st1",
        roles=["student"],
        permissions=["challenge.view", "challenge.attempt"],
    )
    client = _make_app(user)
    assert client.get("/admin-challenge").status_code == 403