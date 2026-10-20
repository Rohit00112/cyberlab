"""Compare Rust's live RBAC decisions to the existing Python role policy.

Run after `cargo build --locked` from the repository root. Uses an ephemeral
local HTTP port and a test-only token; no database, credentials or network
services are needed. CI runs this whenever the RBAC matrix changes.
"""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
POLICY = ROOT / "apps/api/app/core/permissions.py"
BINARY = ROOT / "apps/security-core/target/debug/cyberlab-security-core"


def load_policy():
    spec = importlib.util.spec_from_file_location("cyberlab_role_policy", POLICY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expand(role_map, roles):
    seen = set()
    permissions = []
    for role in sorted(roles):
        for permission in sorted(role_map.get(role, set())):
            if permission not in seen:
                seen.add(permission)
                permissions.append(permission)
    return permissions


def main():
    if not BINARY.is_file():
        raise SystemExit("Build Rust first: cd apps/security-core && cargo build --locked")
    policy = load_policy()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    token = "local-policy-parity-test-token-only-1234567890123456"
    env = dict(os.environ, PORT=str(port), RUST_CORE_SHARED_TOKEN=token)
    server = subprocess.Popen([str(BINARY)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = f"http://127.0.0.1:{port}/v1/authorization"

        def check(roles, permission):
            body = json.dumps({"roles": roles, "permission": permission}).encode()
            request = urllib.request.Request(
                url, data=body, headers={
                    "Content-Type": "application/json", "x-internal-token": token,
                }
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                actual = json.load(response)
            expected_permissions = expand(policy.ROLE_PERMISSIONS, roles)
            expected_allowed = None if permission is None else policy.has_permission(roles, permission)
            assert actual == {
                "permissions": expected_permissions, "allowed": expected_allowed,
            }, (roles, permission, actual)

        for _ in range(50):
            try:
                check([], None)
                break
            except urllib.error.URLError:
                if server.poll() is not None:
                    raise RuntimeError("Rust service stopped before becoming ready") from None
                time.sleep(0.1)
        else:
            raise RuntimeError("Rust service did not become ready")

        known_roles = sorted(policy.ROLE_PERMISSIONS)
        universe = sorted({p for items in policy.ROLE_PERMISSIONS.values() for p in items})
        combinations = (
            [[]]
            + [[role] for role in known_roles]
            + [["unrecognized-role"]]
            + [["student", "faculty"], ["researcher", "lab_admin"], known_roles]
        )
        cases = 0
        for roles in combinations:
            for permission in [None, "nonexistent.permission", *universe]:
                check(roles, permission)
                cases += 1
        print(f"Rust/Python RBAC policy parity passed: {cases} permission decisions")
    finally:
        server.terminate()
        try:
            server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


if __name__ == "__main__":
    main()
