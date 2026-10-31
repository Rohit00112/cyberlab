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


async def record_incorrect_attempt(
    challenge_id: str, user_id: str, roles: list[str], ip_address: str | None
) -> None:
    result = await _post("/v1/submissions/incorrect", {
        "challenge_id": challenge_id, "user_id": user_id,
        "roles": roles, "ip_address": ip_address,
    })
    if result.get("outcome") == "not_found":
        raise HTTPException(status_code=404, detail="Challenge not found")
    if result.get("outcome") != "recorded":
        raise HTTPException(status_code=503, detail="Invalid Rust security core response")


async def reveal_hint_in_rust(
    challenge_id: str, user_id: str, roles: list[str],
    ip_address: str | None, hint_index: int,
) -> int:
    result = await _post("/v1/hints/reveal", {
        "challenge_id": challenge_id, "actor_id": user_id,
        "roles": roles, "ip_address": ip_address, "hint_index": hint_index,
    })
    if not isinstance(result, dict):
        raise HTTPException(status_code=503, detail="Invalid Rust hint response")
    outcome = result.get("outcome")
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="Challenge not found")
    if outcome == "negative_index":
        raise HTTPException(status_code=400, detail="Invalid hint index")
    if outcome == "invalid_index":
        total = result.get("total_hints")
        if type(total) is not int or total < 0:
            raise HTTPException(status_code=503, detail="Invalid Rust hint response")
        raise HTTPException(status_code=400, detail=f"Only {total} hints available")
    if outcome == "out_of_order":
        next_index = result.get("next_index")
        if type(next_index) is not int or next_index < 0:
            raise HTTPException(status_code=503, detail="Invalid Rust hint response")
        raise HTTPException(
            status_code=409, detail=f"Reveal hints in order — hint {next_index} next"
        )
    count = result.get("revealed_count")
    if outcome not in {"revealed", "already_revealed"} or type(count) is not int or count < 0:
        raise HTTPException(status_code=503, detail="Invalid Rust hint response")
    return count


async def record_correct_solve(
    challenge_id: str, user_id: str, roles: list[str], ip_address: str | None,
    candidate: str, lab_id: str | None,
) -> tuple[str, int]:
    result = await _post("/v1/submissions/correct", {
        "challenge_id": challenge_id, "user_id": user_id, "roles": roles,
        "ip_address": ip_address, "candidate": candidate, "lab_id": lab_id,
    })
    outcome, points = result.get("outcome"), result.get("points")
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="Challenge not found")
    if outcome == "lab_unavailable":
        raise HTTPException(status_code=409, detail="Lab session is unavailable")
    if outcome == "stale_flag":
        raise HTTPException(status_code=409, detail="Flag has changed; retry submission")
    if outcome not in {"solved", "already_solved"} or type(points) is not int or points < 0:
        raise HTTPException(status_code=503, detail="Invalid Rust security core response")
    return outcome, points


async def create_competition_in_rust(
    actor_id: str, roles: list[str], ip_address: str | None, slug: str, fields: dict
) -> str:
    result = await _post("/v1/competitions/create", {
        "actor_id": actor_id, "roles": roles, "ip_address": ip_address,
        "slug": slug, "fields": fields,
    })
    if result.get("outcome") != "created":
        raise HTTPException(status_code=503, detail="Invalid Rust competition response")
    from uuid import UUID
    try:
        return str(UUID(result["competition_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Invalid Rust competition ID") from exc


async def edit_competition_in_rust(
    competition_id: str, actor_id: str, roles: list[str],
    ip_address: str | None, changes: dict,
) -> None:
    result = await _post("/v1/competitions/edit", {
        "competition_id": competition_id, "actor_id": actor_id,
        "roles": roles, "ip_address": ip_address, "changes": changes,
    })
    if not isinstance(result, dict):
        raise HTTPException(status_code=503, detail="Invalid Rust competition response")
    if result.get("outcome") == "not_found":
        raise HTTPException(status_code=404, detail="Competition not found")
    if result.get("outcome") == "locked":
        raise HTTPException(
            status_code=409,
            detail="Competition is already live or finished — fields are locked.",
        )
    if result.get("outcome") != "updated":
        raise HTTPException(status_code=503, detail="Invalid Rust competition response")


async def link_competition_challenge_in_rust(
    action: str, competition_id: str, challenge_id: str,
    actor_id: str, roles: list[str], ip_address: str | None,
    points: int | None = None,
) -> None:
    if action not in {"add", "remove"}:
        raise HTTPException(status_code=503, detail="Invalid competition link action")
    result = await _post(f"/v1/competitions/challenges/{action}", {
        "competition_id": competition_id, "challenge_id": challenge_id,
        "actor_id": actor_id, "roles": roles, "ip_address": ip_address,
        "points": points,
    })
    if not isinstance(result, dict):
        raise HTTPException(status_code=503, detail="Invalid Rust competition response")
    outcome = result.get("outcome")
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="Competition not found")
    if outcome == "challenge_not_found":
        raise HTTPException(status_code=404, detail="Challenge not found")
    if outcome == "locked":
        raise HTTPException(
            status_code=409,
            detail="Challenge set is locked once competition leaves registration.",
        )
    if outcome == "duplicate":
        raise HTTPException(status_code=409, detail="Challenge already in competition")
    if outcome != {"add": "added", "remove": "removed"}[action]:
        raise HTTPException(status_code=503, detail="Invalid Rust competition response")


async def change_competition_registration_in_rust(
    action: str, competition_id: str, actor_id: str,
    roles: list[str], ip_address: str | None,
) -> None:
    if action not in {"register", "unregister"}:
        raise HTTPException(status_code=503, detail="Invalid competition registration action")
    result = await _post(f"/v1/competitions/{action}", {
        "competition_id": competition_id, "actor_id": actor_id,
        "roles": roles, "ip_address": ip_address,
    })
    if not isinstance(result, dict):
        raise HTTPException(status_code=503, detail="Invalid Rust competition response")
    outcome = result.get("outcome")
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="Competition not found")
    if outcome == "closed":
        current = result.get("current_status")
        if current not in {
            "draft", "registration", "scheduled", "live", "finished", "archived",
        }:
            raise HTTPException(status_code=503, detail="Invalid Rust competition response")
        raise HTTPException(
            status_code=409, detail=f"Registration is not open (status '{current}').",
        )
    if outcome == "already_registered":
        raise HTTPException(status_code=409, detail="Already registered")
    if outcome == "not_registered":
        raise HTTPException(status_code=409, detail="Not registered")
    if outcome != {"register": "registered", "unregister": "unregistered"}[action]:
        raise HTTPException(status_code=503, detail="Invalid Rust competition response")


async def change_competition_team_in_rust(
    action: str, competition_id: str, actor_id: str,
    roles: list[str], ip_address: str | None,
    *, name: str | None = None, team_id: str | None = None,
) -> None:
    if action not in {"create", "join"}:
        raise HTTPException(status_code=503, detail="Invalid competition team action")
    result = await _post(f"/v1/competitions/teams/{action}", {
        "competition_id": competition_id, "actor_id": actor_id,
        "roles": roles, "ip_address": ip_address,
        "name": name, "team_id": team_id,
    })
    if not isinstance(result, dict):
        raise HTTPException(status_code=503, detail="Invalid Rust competition response")
    outcome = result.get("outcome")
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="Competition not found")
    if outcome == "closed":
        current = result.get("current_status")
        if current not in {
            "draft", "registration", "scheduled", "live", "finished", "archived",
        }:
            raise HTTPException(status_code=503, detail="Invalid Rust competition response")
        raise HTTPException(
            status_code=409, detail=f"Registration is not open (status '{current}').",
        )
    if outcome == "disabled":
        raise HTTPException(status_code=409, detail="Teams are not enabled for this competition.")
    if outcome == "team_not_found" and action == "join":
        raise HTTPException(status_code=404, detail="Team not found")
    if outcome == "not_registered":
        detail = {
            "create": "Register for the competition before creating a team.",
            "join": "Register for the competition before joining a team.",
        }[action]
        raise HTTPException(status_code=409, detail=detail)
    if outcome == "already_on_team":
        raise HTTPException(
            status_code=409, detail="You are already on a team in this competition.",
        )
    if outcome == "full" and action == "join":
        maximum = result.get("max_team_size")
        if type(maximum) is not int or not 1 <= maximum <= 10:
            raise HTTPException(status_code=503, detail="Invalid Rust competition response")
        raise HTTPException(status_code=409, detail=f"Team is full (max {maximum}).")
    if outcome != {"create": "created", "join": "joined"}[action]:
        raise HTTPException(status_code=503, detail="Invalid Rust competition response")


async def set_competition_frozen_in_rust(
    competition_id: str, actor_id: str, roles: list[str],
    ip_address: str | None, frozen: bool,
) -> None:
    result = await _post("/v1/competitions/freeze", {
        "competition_id": competition_id, "actor_id": actor_id,
        "roles": roles, "ip_address": ip_address, "frozen": frozen,
    })
    if not isinstance(result, dict):
        raise HTTPException(status_code=503, detail="Invalid Rust competition response")
    if result.get("outcome") == "not_found":
        raise HTTPException(status_code=404, detail="Competition not found")
    if result.get("outcome") != "updated":
        raise HTTPException(status_code=503, detail="Invalid Rust competition response")


async def persist_competition_transition_in_rust(
    competition_id: str, action: str, actor_id: str,
    roles: list[str], ip_address: str | None,
) -> str:
    transitions = {
        "start_registration": ("draft", "registration"),
        "schedule": ("registration", "scheduled"),
        "start": ("scheduled", "live"),
        "finish": ("live", "finished"),
        "archive": ("finished", "archived"),
    }
    if action not in transitions:
        raise HTTPException(status_code=400, detail="Unknown transition")
    result = await _post("/v1/competitions/transition/persist", {
        "competition_id": competition_id, "action": action,
        "actor_id": actor_id, "roles": roles, "ip_address": ip_address,
    })
    if not isinstance(result, dict):
        raise HTTPException(status_code=503, detail="Invalid Rust competition response")
    outcome = result.get("outcome")
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="Competition not found")
    if outcome == "unknown_action":
        raise HTTPException(status_code=400, detail="Unknown transition")
    if outcome == "invalid_transition":
        current = result.get("current_status")
        if not isinstance(current, str) or current not in {
            "draft", "registration", "scheduled", "live", "finished", "archived",
        }:
            raise HTTPException(status_code=503, detail="Invalid Rust competition response")
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot {action}: competition is '{current}', "
                f"expected '{transitions[action][0]}'."
            ),
        )
    if outcome == "too_early":
        raise HTTPException(
            status_code=409,
            detail="Competition cannot start before its scheduled start time.",
        )
    if outcome == "missing_schedule":
        raise HTTPException(
            status_code=400, detail="Set start_at and end_at before scheduling.",
        )
    if (
        outcome != "updated"
        or result.get("current_status") != transitions[action][0]
        or result.get("next_status") != transitions[action][1]
    ):
        raise HTTPException(status_code=503, detail="Invalid Rust competition response")
    return transitions[action][1]


async def auto_transition_competitions_in_rust() -> int:
    result = await _post("/v1/competitions/transition/auto", {})
    if not isinstance(result, dict):
        raise HTTPException(status_code=503, detail="Invalid Rust scheduler response")
    changed = result.get("changed")
    # Each phase processes at most 250 rows, including events that cross two
    # lifecycle states in one sweep.
    if type(changed) is not int or not 0 <= changed <= 500:
        raise HTTPException(status_code=503, detail="Invalid Rust scheduler response")
    return changed


async def extend_lab_in_rust(
    lab_id: str, actor_id: str, roles: list[str], ip_address: str | None,
    additional_minutes: int, max_expiry_minutes: int,
) -> None:
    result = await _post("/v1/labs/extend", {
        "lab_id": lab_id, "actor_id": actor_id, "roles": roles,
        "ip_address": ip_address, "additional_minutes": additional_minutes,
        "max_expiry_minutes": max_expiry_minutes,
    })
    if not isinstance(result, dict):
        raise HTTPException(status_code=503, detail="Invalid Rust lab response")
    outcome = result.get("outcome")
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="Lab not found")
    if outcome == "not_running":
        current = result.get("current_status")
        if current not in {
            "queued", "provisioning", "starting", "stopping", "stopped",
            "resetting", "terminating", "terminated", "failed", "expired",
            "error",
        }:
            raise HTTPException(status_code=503, detail="Invalid Rust lab response")
        raise HTTPException(
            status_code=400,
            detail=f"Cannot extend lab in status '{current}' (must be running)",
        )
    if outcome == "expired":
        raise HTTPException(
            status_code=400,
            detail="Cannot extend an already expired lab. Please reset or relaunch.",
        )
    if outcome != "extended" or result.get("current_status") is not None:
        raise HTTPException(status_code=503, detail="Invalid Rust lab response")


async def finalize_lab_stop_in_rust(
    lab_id: str, actor_id: str, roles: list[str],
    ip_address: str | None, expected_provider_ref: str | None,
) -> None:
    """Persist the confirmed provider stop and its audit in one Rust transaction."""
    result = await _post("/v1/labs/stop/finalize", {
        "lab_id": lab_id, "actor_id": actor_id, "roles": roles,
        "ip_address": ip_address, "expected_provider_ref": expected_provider_ref,
    })
    if not isinstance(result, dict):
        raise HTTPException(status_code=503, detail="Invalid Rust lab response")
    outcome = result.get("outcome")
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="Lab not found")
    if outcome == "not_running":
        current = result.get("current_status")
        if current not in {
            "queued", "provisioning", "starting", "stopping",
            "resetting", "terminating", "terminated", "failed", "expired", "error",
        }:
            raise HTTPException(status_code=503, detail="Invalid Rust lab response")
        raise HTTPException(
            status_code=409, detail=f"Cannot stop lab in status '{current}'",
        )
    if outcome == "provider_missing":
        raise HTTPException(status_code=503, detail="Lab provider reference is missing")
    if outcome == "stale_provider":
        raise HTTPException(
            status_code=409, detail="Lab provider changed during stop; retry",
        )
    if outcome not in {"stopped", "already_stopped"} or result.get("current_status") is not None:
        raise HTTPException(status_code=503, detail="Invalid Rust lab response")


async def finalize_lab_terminal_in_rust(
    action: str, lab_id: str, actor_id: str, roles: list[str],
    ip_address: str | None, expected_provider_ref: str | None,
) -> None:
    """Commit a provider-confirmed expiry/termination and audit in Rust."""
    if action not in {"expire", "terminate"}:
        raise ValueError("Invalid lab terminal action")
    result = await _post("/v1/labs/terminal/finalize", {
        "action": action, "lab_id": lab_id, "actor_id": actor_id,
        "roles": roles, "ip_address": ip_address,
        "expected_provider_ref": expected_provider_ref,
    })
    if not isinstance(result, dict):
        raise HTTPException(status_code=503, detail="Invalid Rust lab response")
    outcome = result.get("outcome")
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="Lab not found")
    if outcome == "state_changed":
        current = result.get("current_status")
        if current not in {
            "provisioning", "starting", "resetting", "stopping", "terminating",
        }:
            raise HTTPException(status_code=503, detail="Invalid Rust lab response")
        raise HTTPException(
            status_code=409, detail=f"Lab state changed during {action}: '{current}'",
        )
    if outcome == "provider_missing":
        raise HTTPException(status_code=503, detail="Lab provider reference is missing")
    if outcome == "stale_provider":
        raise HTTPException(
            status_code=409, detail=f"Lab provider changed during {action}; retry",
        )
    if outcome not in {"expired", "already_expired"} or result.get("current_status") is not None:
        raise HTTPException(status_code=503, detail="Invalid Rust lab response")


async def claim_provisioning_job_in_rust(job_id: str) -> bool:
    """Claim one pending job and its queued lab atomically before provider I/O."""
    result = await _post("/v1/labs/provisioning/claim", {"job_id": job_id})
    if not isinstance(result, dict) or set(result) != {"outcome"}:
        raise HTTPException(status_code=503, detail="Invalid Rust provisioning response")
    if result["outcome"] == "claimed":
        return True
    if result["outcome"] == "unavailable":
        return False
    raise HTTPException(status_code=503, detail="Invalid Rust provisioning response")


async def start_provisioning_job_in_rust(job_id: str) -> bool:
    """Commit provisioning -> starting with audit before provider creation."""
    result = await _post("/v1/labs/provisioning/start", {"job_id": job_id})
    if not isinstance(result, dict) or set(result) != {"outcome"}:
        raise HTTPException(status_code=503, detail="Invalid Rust provisioning response")
    if result["outcome"] == "started":
        return True
    if result["outcome"] == "unavailable":
        return False
    raise HTTPException(status_code=503, detail="Invalid Rust provisioning response")


async def complete_provisioning_job_in_rust(
    *, job_id: str, provider_ref: str, container_name: str,
    flag_hash: str, flag_path: str, connection_hint: str, expiry_minutes: int,
) -> bool:
    """Atomically record the provider result, lease, completed job and audit."""
    result = await _post("/v1/labs/provisioning/complete", {
        "job_id": job_id, "provider_ref": provider_ref,
        "container_name": container_name, "flag_hash": flag_hash,
        "flag_path": flag_path, "connection_hint": connection_hint,
        "expiry_minutes": expiry_minutes,
    })
    if not isinstance(result, dict) or set(result) != {"outcome"}:
        raise HTTPException(status_code=503, detail="Invalid Rust provisioning response")
    if result["outcome"] == "completed":
        return True
    if result["outcome"] == "unavailable":
        return False
    raise HTTPException(status_code=503, detail="Invalid Rust provisioning response")


async def fail_provisioning_job_in_rust(
    *, job_id: str, error_message: str, cleanup_failed: bool,
    provider_ref: str | None,
) -> bool:
    """Atomically persist failure and required audit after provider compensation."""
    result = await _post("/v1/labs/provisioning/fail", {
        "job_id": job_id, "error_message": error_message,
        "cleanup_failed": cleanup_failed, "provider_ref": provider_ref,
    })
    if not isinstance(result, dict) or set(result) != {"outcome"}:
        raise HTTPException(status_code=503, detail="Invalid Rust provisioning response")
    if result["outcome"] == "failed":
        return True
    if result["outcome"] == "unavailable":
        return False
    raise HTTPException(status_code=503, detail="Invalid Rust provisioning response")


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


async def create_challenge_in_rust(
    actor_id: str, roles: list[str], ip_address: str | None,
    slug: str, fields: dict,
) -> str:
    result = await _post("/v1/challenges/create", {
        "actor_id": actor_id, "roles": roles, "ip_address": ip_address,
        "slug": slug, "fields": fields,
    })
    if result.get("outcome") != "created":
        raise HTTPException(status_code=503, detail="Invalid Rust security core response")
    try:
        from uuid import UUID

        return str(UUID(result["challenge_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=503, detail="Invalid Rust security core response"
        ) from exc


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
