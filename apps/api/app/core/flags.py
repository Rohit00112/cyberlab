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


def guest_flag_command(flag_path: str, flag: str) -> list[str]:
    """Short-lived Linux VM initializer; the guest agent must observe exit 0."""
    return [
        "/bin/sh", "-c",
        f"printf '%s\\n' {shlex.quote(flag)} > {shlex.quote(flag_path)}",
    ]


def validate_guest_flag_command(cmd: list[str]) -> None:
    """Limit hypervisor guest execution to the generated one-shot flag writer."""
    if (
        not isinstance(cmd, list) or len(cmd) != 3
        or cmd[:2] != ["/bin/sh", "-c"]
        or not isinstance(cmd[2], str)
        or not cmd[2].startswith("printf '%s\\n' ")
        or " > " not in cmd[2]
        or "\n" in cmd[2] or "\r" in cmd[2]
        or len(cmd[2]) > 1000
    ):
        raise ValueError("Only the built-in guest flag initializer may run")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "challenge"
