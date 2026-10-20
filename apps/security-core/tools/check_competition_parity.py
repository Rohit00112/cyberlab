"""Live Rust/Python competition-transition contract check, using only stdlib.

Run after cargo build --locked from the security-core directory. Reads the
Python transition map from source to catch action changes in future PRs.
"""

from __future__ import annotations

import ast
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BINARY = ROOT / "apps/security-core/target/debug/cyberlab-security-core"
POLICY = ROOT / "apps/api/app/core/competition_transitions.py"


def python_transitions():
    parsed = ast.parse(POLICY.read_text(encoding="utf-8"))
    for node in parsed.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "TRANSITIONS"
        ):
            return ast.literal_eval(node.value)
    raise RuntimeError("Python TRANSITIONS map is missing")


def reference(current, action, start_at, end_at, now, transitions):
    if action == "auto":
        if current == "scheduled" and start_at is not None and start_at <= now:
            return {"next_status": "live", "error_code": None}
        if current == "live" and end_at is not None and end_at <= now:
            return {"next_status": "finished", "error_code": None}
        return {"next_status": None, "error_code": None}
    next_status = None
    error = None
    if action not in transitions:
        error = "unknown_action"
    else:
        source, destination = transitions[action]
        if current != source:
            error = "invalid_transition"
        elif action == "schedule" and (start_at is None or end_at is None):
            error = "missing_schedule"
        elif action == "start" and start_at is not None and start_at > now + 300_000:
            error = "too_early"
        else:
            next_status = destination
    return {"next_status": next_status, "error_code": error}


def main():
    if not BINARY.exists():
        raise SystemExit("Build the Rust service with cargo build --locked first")
    transitions = python_transitions()
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    token = "test-comp-transition-parity-2026-1234567890123456"
    server = subprocess.Popen(
        [str(BINARY)],
        env={**os.environ, "PORT": str(port), "RUST_CORE_SHARED_TOKEN": token},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        url = f"http://127.0.0.1:{port}/v1/competition-transition"

        def call(payload):
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "x-internal-token": token},
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                return json.load(response)

        ready = False
        for _ in range(50):
            try:
                call({"current": "draft", "action": "auto", "now": 0})
                ready = True
                break
            except urllib.error.URLError:
                if server.poll() is not None:
                    raise RuntimeError("Rust server terminated unexpectedly") from None
                time.sleep(0.1)
        if not ready:
            raise RuntimeError("Rust server failed to start")

        now = 1_800_000_000_000
        dates = [
            (None, None),
            (now - 60_000, now + 60_000),
            (now, now),
            (now + 300_000, now + 300_000),
            (now + 300_001, now + 300_001),
            (now + 3_600_000, now - 1),
            (now - 1, now - 1),
            (None, now + 60_000),
            (now + 60_000, None),
        ]
        count = 0
        for current in ["draft", "registration", "scheduled", "live", "finished", "archived"]:
            for action in [*transitions, "auto", "unrecognized"]:
                for start_at, end_at in dates:
                    payload = {
                        "current": current,
                        "action": action,
                        "start_at": start_at,
                        "end_at": end_at,
                        "now": now,
                    }
                    actual = call(payload)
                    expected = reference(current, action, start_at, end_at, now, transitions)
                    assert actual == expected, (payload, expected, actual)
                    count += 1
        print(f"Rust/Python competition parity passed: {count} transition decisions")
    finally:
        server.terminate()
        try:
            server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


if __name__ == "__main__":
    main()
