"""FastAPI rate-limiting dependencies (PRD §51).

Rate limits are bucketed per authenticated user so a student brute-forcing
flags or hints is throttled without affecting other users.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.api.deps import CurrentUser, get_current_user
from app.core.ratelimit import check_rate_limit


def rate_limit(scope: str, limit: int, window_seconds: int):
    async def dependency(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> None:
        allowed = await check_rate_limit(
            f"user:{user.id}:{scope}",
            limit=limit,
            window_seconds=window_seconds,
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests — please slow down.",
            )
        return None

    dependency.__name__ = f"rate_limit_{scope}"

    return dependency