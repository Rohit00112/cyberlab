"""Verify Rust authorization fail-closed semantics and Python fallback."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.core import authorization, rust_engine
from app.core.permissions import ROLE_PERMISSIONS


@pytest.mark.asyncio
async def test_python_fallback_preserves_role_expansion_order(monkeypatch):
    monkeypatch.setattr(authorization, "get_settings", lambda: SimpleNamespace(rust_core_url=""))
    roles = ["student", "faculty", "student"]
    actual = await authorization.expand_permissions(roles)
    expected = list(dict.fromkeys(
        permission
        for role in sorted(roles)
        for permission in sorted(ROLE_PERMISSIONS.get(role, set()))
    ))
    assert actual == expected


@pytest.mark.asyncio
async def test_rust_authorization_is_authoritative(monkeypatch):
    monkeypatch.setattr(
        authorization, "get_settings", lambda: SimpleNamespace(rust_core_url="http://security-core:8081")
    )
    mock = AsyncMock(return_value=(["challenge.view"], False))
    monkeypatch.setattr(authorization, "authorize_roles", mock)
    assert not await authorization.check_permission(["sysadmin"], "challenge.edit")
    mock.assert_awaited_once_with(["sysadmin"], "challenge.edit")


@pytest.mark.asyncio
async def test_rust_failure_never_falls_back(monkeypatch):
    monkeypatch.setattr(
        authorization, "get_settings", lambda: SimpleNamespace(rust_core_url="http://security-core:8081")
    )
    monkeypatch.setattr(
        authorization, "authorize_roles",
        AsyncMock(side_effect=HTTPException(status_code=503, detail="Rust unavailable")),
    )
    with pytest.raises(HTTPException) as error:
        await authorization.check_permission(["sysadmin"], "user.manage")
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_adapter_rejects_malformed_authorization(monkeypatch):
    monkeypatch.setattr(
        rust_engine, "_post", AsyncMock(return_value={"allowed": 1, "permissions": []})
    )
    with pytest.raises(HTTPException) as error:
        await rust_engine.authorize_roles(["student"], "challenge.view")
    assert error.value.status_code == 503


def test_access_dependency_uses_rust_policy_even_if_user_permissions_forged(monkeypatch):
    monkeypatch.setattr(
        authorization, "get_settings", lambda: SimpleNamespace(rust_core_url="http://security-core:8081")
    )
    monkeypatch.setattr(
        authorization, "authorize_roles", AsyncMock(return_value=(["challenge.view"], False)),
    )
    user = CurrentUser(
        id="00000000-0000-0000-0000-000000000001",
        keycloak_sub="test-student", roles=["student"], permissions=["*"],
    )
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: user

    @app.get("/restricted")
    async def restricted(_=Depends(require_permission("user.manage"))):  # noqa: B008
        return {"ok": True}

    with TestClient(app) as client:
        assert client.get("/restricted").status_code == 403
