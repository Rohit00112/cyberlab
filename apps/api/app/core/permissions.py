"""Role -> permission mapping (see PRD §8).

Granular permissions are derived from Keycloak realm roles server-side.
``sysadmin`` has the wildcard; everything else is scoped per role.
"""

from __future__ import annotations

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "sysadmin": {"*", "user.view", "user.manage"},
    "faculty": {
        "challenge.view",
        "challenge.create",
        "challenge.edit",
        "challenge.publish",
        "submission.review",
        "analytics.view",
        "audit.view",
        "lab.launch",
        "lab.reset",
        "lab.admin",
        "competition.create",
        "competition.manage",
        "skill.view",
        "skill.manage",
        "badge.view",
        "badge.manage",
    },
    "competition_organizer": {
        "competition.create",
        "competition.manage",
        "challenge.view",
        "analytics.view",
        "skill.view",
        "badge.view",
    },
    "lab_admin": {
        "lab.admin",
        "lab.launch",
        "lab.reset",
        "challenge.view",
        "analytics.view",
        "audit.view",
        "skill.view",
        "badge.view",
    },
    "researcher": {
        "analytics.view",
        "analytics.research",
        "challenge.view",
        "skill.view",
        "badge.view",
    },
    "student": {
        "challenge.view",
        "challenge.attempt",
        "lab.launch",
        "lab.reset",
        "submission.create",
        "skill.view",
        "badge.view",
    },
}


def has_permission(roles: list[str], permission: str) -> bool:
    perms = {p for role in roles for p in ROLE_PERMISSIONS.get(role, set())}
    if "*" in perms:
        return True
    return permission in perms
