"""Role authorization facade; Rust owns decisions when the core is configured.

Keycloak verifies identity and supplies realm roles; only the internal security
core evaluates those roles when Rust mode is enabled. Connectivity failures
are propagated as 503 to prevent an unintended Python fallback.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.permissions import ROLE_PERMISSIONS, has_permission
from app.core.rust_engine import authorize_roles


async def expand_permissions(roles: list[str]) -> list[str]:
    if get_settings().rust_core_url:
        permissions, _ = await authorize_roles(roles)
        return permissions
    seen: set[str] = set()
    permissions: list[str] = []
    for role in sorted(roles):
        for permission in sorted(ROLE_PERMISSIONS.get(role, set())):
            if permission not in seen:
                seen.add(permission)
                permissions.append(permission)
    return permissions


async def check_permission(roles: list[str], permission: str) -> bool:
    if get_settings().rust_core_url:
        _permissions, allowed = await authorize_roles(roles, permission)
        assert allowed is not None
        return allowed
    return has_permission(roles, permission)
