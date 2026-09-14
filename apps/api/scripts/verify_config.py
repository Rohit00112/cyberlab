"""Fail-fast configuration guard for production (parse once at deploy time).

Rejects placeholder development secrets when ``ENVIRONMENT=production`` so a
misconfigured container cannot silently boot with known credentials.

Usage::

    python -m scripts.verify_config  # exits 0 on healthy config, 1 otherwise

Runs automatically in the production image entrypoint (see Dockerfile).
"""
from __future__ import annotations

import os
import sys

PLACEHOLDERS = ("change-me", "dev-secret", "dev-only", "admin", "<", "${")

REQUIRED = (
    "DATABASE_URL",
    "OIDC_ISSUER_URL",
    "OIDC_CLIENT_ID",
    "OIDC_CLIENT_SECRET",
    "APP_SECRET",
)


def _placeholder(secret: str) -> bool:
    return any(token in secret for token in PLACEHOLDERS)


def verify(env: dict[str, str] | None = None) -> list[str]:
    env = os.environ if env is None else env
    problems: list[str] = []
    environment = env.get("ENVIRONMENT", "development").strip().lower()

    for name in REQUIRED:
        if not env.get(name):
            problems.append(f"missing required env var: {name}")

    if environment == "production":
        for name in REQUIRED:
            value = env.get(name, "")
            if value and _placeholder(value):
                problems.append(f"placeholder secret present in production: {name}")

    return problems


def main() -> None:
    problems = verify()
    if problems:
        for problem in problems:
            print(f"config error: {problem}", file=sys.stderr)
        raise SystemExit(1)
    print("config ok")


if __name__ == "__main__":
    main()