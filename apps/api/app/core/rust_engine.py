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
    try:
        endpoint = urlsplit(settings.rust_core_url)
        port = endpoint.port
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Invalid Rust security core endpoint") from exc
    if (
        endpoint.scheme != "http"
        or endpoint.hostname not in {"security-core", "127.0.0.1", "localhost"}
        or (endpoint.hostname == "security-core" and port != 8081)
        or (endpoint.hostname != "security-core" and port is None)
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


async def publish_challenge_in_rust(
    challenge_id: str, actor_id: str, roles: list[str], ip_address: str | None
) -> int:
    result = await _post("/v1/challenges/publish", {
        "challenge_id": challenge_id,
        "actor_id": actor_id,
        "roles": roles,
        "ip_address": ip_address,
    })
    outcome = result.get("outcome")
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="Challenge not found")
    if outcome == "missing_flag":
        raise HTTPException(status_code=400, detail="A flag is required before publishing")
    if outcome != "published" or type(result.get("version")) is not int:
        raise HTTPException(status_code=503, detail="Invalid Rust security core response")
    return result["version"]


async def delete_challenge_in_rust(
    challenge_id: str, actor_id: str, roles: list[str], ip_address: str | None
) -> None:
    result = await _post("/v1/challenges/delete", {
        "challenge_id": challenge_id,
        "actor_id": actor_id,
        "roles": roles,
        "ip_address": ip_address,
    })
    outcome = result.get("outcome")
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="Challenge not found")
    if outcome != "deleted":
        raise HTTPException(status_code=503, detail="Invalid Rust security core response")


async def edit_challenge_in_rust(
    challenge_id: str, actor_id: str, roles: list[str],
    ip_address: str | None, changes: dict,
) -> int:
    result = await _post("/v1/challenges/edit", {
        "challenge_id": challenge_id, "actor_id": actor_id,
        "roles": roles, "ip_address": ip_address, "changes": changes,
    })
    if result.get("outcome") == "not_found":
        raise HTTPException(status_code=404, detail="Challenge not found")
    if result.get("outcome") == "missing_flag":
        raise HTTPException(status_code=400, detail="Published challenges require a flag")
    if result.get("outcome") != "updated" or type(result.get("version")) is not int:
        raise HTTPException(status_code=503, detail="Invalid Rust security core response")
    return result["version"]


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


async def authorize_roles(
    roles: list[str], permission: str | None = None
) -> tuple[list[str], bool | None]:
    """Expand the role union and, optionally, evaluate an access decision."""
    result = await _post("/v1/authorization", {"roles": roles, "permission": permission})
    permissions = result.get("permissions") if isinstance(result, dict) else None
    allowed = result.get("allowed") if isinstance(result, dict) else None
    if (
        not isinstance(permissions, list)
        or any(not isinstance(p, str) or not p for p in permissions)
        or len(permissions) != len(set(permissions))
        or (allowed is not None and type(allowed) is not bool)
        or (permission is None and allowed is not None)
        or (permission is not None and type(allowed) is not bool)
    ):
        raise HTTPException(status_code=503, detail="Invalid Rust authorization response")
    return permissions, allowed


async def competition_transition(
    current: str,
    action: str,
    *,
    start_at: int | None,
    end_at: int | None,
    now: int,
) -> tuple[str | None, str | None]:
    """Evaluate a competition state change using Rust's time-aware rules."""
    result = await _post(
        "/v1/competition-transition",
        {
            "current": current,
            "action": action,
            "start_at": start_at,
            "end_at": end_at,
            "now": now,
        },
    )
    if not isinstance(result, dict):
        raise HTTPException(status_code=503, detail="Invalid Rust competition response")
    next_status = result.get("next_status")
    error_code = result.get("error_code")
    known_statuses = {
        "draft", "registration", "scheduled", "live", "finished", "archived",
    }
    known_errors = {
        "unknown_action", "invalid_transition", "missing_schedule", "too_early",
    }
    if (
        next_status is not None
        and (not isinstance(next_status, str) or next_status not in known_statuses)
        or error_code is not None
        and (not isinstance(error_code, str) or error_code not in known_errors)
        or next_status is not None and error_code is not None
        or next_status is None and error_code is None and action != "auto"
    ):
        raise HTTPException(status_code=503, detail="Invalid Rust competition response")
    return next_status, error_code


async def catalog_page(
    *, editor: bool, category: str | None, difficulty: str | None,
    status: str | None, limit: int, offset: int,
) -> tuple[list[str], int]:
    result = await _post("/v1/catalog/query", {
        "editor": editor, "category": category, "difficulty": difficulty,
        "status": status, "limit": limit, "offset": offset,
    })
    if not isinstance(result, dict):
        raise HTTPException(status_code=503, detail="Invalid Rust catalog response")
    ids, total = result.get("ids"), result.get("total")
    import uuid

    if (
        not isinstance(ids, list)
        or len(ids) > limit
        or not all(isinstance(value, str) for value in ids)
        or type(total) is not int
        or total < 0
    ):
        raise HTTPException(status_code=503, detail="Invalid Rust catalog response")
    try:
        parsed = [str(uuid.UUID(value)) for value in ids]
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=503, detail="Invalid Rust catalog IDs") from exc
    if len(set(parsed)) != len(parsed):
        raise HTTPException(status_code=503, detail="Duplicate Rust catalog IDs")
    return parsed, total


async def global_leaderboard(limit: int) -> list[dict]:
    import uuid

    result = await _post("/v1/leaderboard", {"limit": limit})
    if not isinstance(result, list) or len(result) > limit:
        raise HTTPException(status_code=503, detail="Invalid Rust leaderboard response")
    for rank, row in enumerate(result, start=1):
        if (
            not isinstance(row, dict)
            or type(row.get("rank")) is not int
            or row["rank"] != rank
            or type(row.get("points")) is not int
            or type(row.get("solved_count")) is not int
            or row["solved_count"] < 1
            or row["points"] < 0
            or row.get("display_name") is not None
            and not isinstance(row["display_name"], str)
        ):
            raise HTTPException(status_code=503, detail="Invalid Rust leaderboard response")
        try:
            uuid.UUID(row["user_id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=503, detail="Invalid Rust leaderboard ID") from exc
    return result
