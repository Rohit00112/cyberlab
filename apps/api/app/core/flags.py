"""Flag handling. Only SHA-256 digests of flags are ever stored.

Never store a plaintext flag in the database or in API responses.
"""
from __future__ import annotations

import hashlib
import re
import secrets

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
    return hash_flag(candidate) == expected_hash


def generate_lab_flag() -> str:
    """Random per-session lab flag (e.g. ``IIC{lab-5f3a...}``)."""
    return f"IIC{{lab-{secrets.token_hex(8)}}}"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "challenge"