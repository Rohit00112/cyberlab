"""Flag handling. Only SHA-256 digests of flags are ever stored.

Never store a plaintext flag in the database or in API responses.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import shlex

DIFFICULTIES = {"beginner", "intermediate", "advanced"}
STATUSES = {"draft", "published", "archived"}
CATEGORIES = {
    "Linux",
    "Networking",
    "Web Security",
    "Cryptography",
    "Digital Forensics",
    "OSINT",
    "System Security",
    "Blue Team",
    "Secure Coding",
    "Cloud Security",
}


def normalize_flag(flag: str) -> str:
    return flag.strip()


def hash_flag(flag: str) -> str:
    if not flag:
        raise ValueError("flag must not be empty")
    return hashlib.sha256(normalize_flag(flag).encode("utf-8")).hexdigest()


def verify_flag(candidate: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_flag(candidate), expected_hash)


def generate_lab_flag() -> str:
    """Random per-session lab flag (e.g. ``IIC{lab-5f3a...}``)."""
    return f"IIC{{lab-{secrets.token_hex(8)}}}"


def lab_flag_command(flag_path: str, flag: str) -> list[str]:
    """Build a shell-safe container command, including admin-defined flag paths."""
    return [
        "/bin/sh", "-c",
        f"printf '%s\\n' {shlex.quote(flag)} > {shlex.quote(flag_path)} && sleep infinity",
    ]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "challenge"
