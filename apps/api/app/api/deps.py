"""Shared API dependencies: identity and authorization."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.oidc import oidc
from app.core.permissions import ROLE_PERMISSIONS, has_permission
from app.db.session import get_db
from app.services.users import sync_user

bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    id: uuid.UUID
    keycloak_sub: str
    email: str | None = None
    display_name: str | None = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = await oidc.decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = await sync_user(db, claims)
    roles = list(claims.get("realm_access", {}).get("roles", []))

    seen: set[str] = set()
    permissions: list[str] = []
    for role in sorted(roles):
        for perm in sorted(ROLE_PERMISSIONS.get(role, set())):
            if perm not in seen:
                seen.add(perm)
                permissions.append(perm)

    return CurrentUser(
        id=user.id,
        keycloak_sub=user.keycloak_sub,
        email=user.email,
        display_name=user.display_name,
        roles=sorted(roles),
        permissions=permissions,
    )


def require_permission(permission: str):
    async def dependency(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if not has_permission(user.roles, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return dependency