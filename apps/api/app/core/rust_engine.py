"""Client for the internal Rust security core.

When enabled, the core is authoritative: failures raise 503 before a flag
submission is recorded. Never send flags to a public or user-chosen endpoint.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from app.core.config import get_settings


async def _post(path: str, payload: dict) -> dict:
    settings = get_settings()
    if not settings.rust_core_url or len(settings.rust_core_shared_token) < 32:
        raise HTTPException(status_code=503, detail="Rust security core is not configured")
    endpoint = urlsplit(settings.rust_core_url)
    if (
        endpoint.scheme != "http"
        or endpoint.hostname not in {"security-core", "127.0.0.1", "localhost"}
        or endpoint.username
        or endpoint.password
        or endpoint.path not in ("", "/")
        or endpoint.query
        or endpoint.fragment
    ):
        raise HTTPException(status_code=503, detail="Invalid Rust security core endpoint")

    try:
        async with httpx.AsyncClient(
            timeout=2.0, trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                f"{settings.rust_core_url.rstrip('/')}{path}",
                headers={"x-internal-token": settings.rust_core_shared_token},
                json=payload,
            )
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=503, detail="Rust security core is unavailable"
        ) from exc


async def verify_flag(candidate: str, expected_sha256: str) -> bool:
    result = await _post("/v1/verify", {
        "candidate": candidate,
        "expected_sha256": expected_sha256,
    })
    if type(result.get("correct")) is not bool:
        raise HTTPException(status_code=503, detail="Invalid Rust security core response")
    return result["correct"]


async def calculate_score(
    *, base_points: int, solve_rank: int, mode: str, penalty: int
) -> int:
    result = await _post("/v1/score", {
        "base_points": base_points,
        "solve_rank": solve_rank,
        "mode": mode,
        "penalty": penalty,
    })
    points = result.get("points")
    if type(points) is not int or points < 0:
        raise HTTPException(status_code=503, detail="Invalid Rust security core response")
    return points


async def can_transition_lab(current: str, target: str) -> bool:
    result = await _post("/v1/lab-transition", {"current": current, "target": target})
    if type(result.get("allowed")) is not bool:
        raise HTTPException(status_code=503, detail="Invalid Rust security core response")
    return result["allowed"]
