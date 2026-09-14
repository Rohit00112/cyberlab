"""Research pseudonymization (Phase 6, PRD §70).

Research exports must never expose real identities. We replace identity columns
with a deterministic HMAC-based ``participant_id`` derived from the Keycloak
subject. Reversing the mapping requires the ``APP_SECRET``, so exported
artifacts are safe to share while remaining joinable across datasets.
"""
from __future__ import annotations

import hashlib
import hmac

from app.core.config import get_settings

PII_KEYS = ("email", "display_name", "displayName", "keycloak_sub", "username")


def participant_id(keycloak_sub: str) -> str:
    """Deterministic, secret-bound pseudonymous id for a Keycloak subject."""
    settings = get_settings()
    return hmac.new(
        settings.app_secret.encode("utf-8"), keycloak_sub.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:16]


def _strip_pii(obj: dict) -> dict:
    for key in PII_KEYS:
        obj.pop(key, None)
    return obj


def pseudonymize_identity(row: dict, sub: str) -> dict:
    """Replaces any identity/email columns with ``participant_id``."""
    row["participant_id"] = participant_id(sub)
    row.pop("user_id", None)
    return _strip_pii(row)