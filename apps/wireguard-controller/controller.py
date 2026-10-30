"""Unix-socket WireGuard peer controller, deployed beside a configured wg interface.

Only a fixed interface, one narrow VPN address range and peer set/remove are
supported. Never accepts shell commands, routing changes or private keys.
"""
from __future__ import annotations

import base64
import hmac
import ipaddress
import json
import os
import re
import socket
import socketserver
import stat
import subprocess
from pathlib import Path

INTERFACE = os.getenv("WG_INTERFACE", "wg0")
SOCKET = os.getenv("WG_CONTROL_SOCKET", "/run/cyberlab-wireguard/control.sock")
TOKEN = os.getenv("WG_CONTROL_TOKEN", "")
EXPECTED_KEY = os.getenv("WG_EXPECTED_PUBLIC_KEY", "")


def valid_key(value: str) -> bool:
    try:
        decoded = base64.b64decode(value, validate=True)
        return (
            len(decoded) == 32 and decoded != bytes(32)
            and base64.b64encode(decoded).decode("ascii") == value
        )
    except (ValueError, TypeError):
        return False


def valid_ip(value: str) -> bool:
    try:
        ip = ipaddress.IPv4Address(value)
        return ip in ipaddress.IPv4Network("10.200.0.0/24") and 2 <= int(ip) % 256 <= 254
    except (ipaddress.AddressValueError, TypeError):
        return False


def invoke(*args: str) -> str:
    completed = subprocess.run(
        ["/usr/bin/wg", *args], check=True, capture_output=True,
        text=True, timeout=10,
    )
    return completed.stdout


def peer_routes() -> dict[str, str]:
    routes = {}
    for line in invoke("show", INTERFACE, "allowed-ips").splitlines():
        fields = line.split()
        if len(fields) == 2:
            routes[fields[0]] = fields[1]
    return routes


def perform(request: dict) -> None:
    if not isinstance(request, dict) or set(request) != {"token", "action", "public_key", "ip"}:
        raise ValueError("Invalid controller request")
    if not isinstance(request["token"], str) or not hmac.compare_digest(
        request["token"], TOKEN,
    ):
        raise ValueError("Unauthorized controller request")
    key, ip = request["public_key"], request["ip"]
    if not isinstance(key, str) or not valid_key(key) or not valid_ip(ip):
        raise ValueError("Invalid peer key or address")
    current = peer_routes()
    target = f"{ip}/32"
    if key in current and current[key] != target:
        raise RuntimeError("Peer already belongs to a different VPN route")
    if request["action"] == "install":
        if any(other != key and route == target for other, route in current.items()):
            raise RuntimeError("VPN route is already assigned to another public key")
        invoke("set", INTERFACE, "peer", key, "allowed-ips", target)
        if peer_routes().get(key) != target:
            raise RuntimeError("Peer installation was not verified")
    elif request["action"] == "remove":
        invoke("set", INTERFACE, "peer", key, "remove")
        if key in peer_routes():
            raise RuntimeError("Peer revocation was not verified")
    else:
        raise ValueError("Invalid peer operation")


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            raw = self.rfile.readline(4097)
            if len(raw) > 4096 or not raw.endswith(b"\n"):
                raise ValueError("Oversized request")
            perform(json.loads(raw))
            response = {"ok": True}
        except (ValueError, TypeError, json.JSONDecodeError, OSError,
                subprocess.SubprocessError, RuntimeError):
            response = {"ok": False}
        self.wfile.write((json.dumps(response) + "\n").encode("ascii"))


def main() -> None:
    if (
        not re.fullmatch(r"[a-zA-Z0-9_-]{1,15}", INTERFACE)
        or len(TOKEN) < 32 or not valid_key(EXPECTED_KEY)
    ):
        raise SystemExit("WireGuard controller requires interface, token and public key")
    if invoke("show", INTERFACE, "public-key").strip() != EXPECTED_KEY:
        raise SystemExit("Configured WireGuard interface does not match expected server key")
    Path(SOCKET).parent.mkdir(parents=True, exist_ok=True)
    if Path(SOCKET).exists():
        if not stat.S_ISSOCK(Path(SOCKET).stat().st_mode):
            raise SystemExit("WireGuard socket path is occupied by a non-socket file")
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            probe.connect(SOCKET)
        except ConnectionRefusedError:
            # Recover only this exact stale listener path after an abrupt exit.
            Path(SOCKET).unlink()
        else:
            raise SystemExit("Another WireGuard controller is already listening")
        finally:
            probe.close()
    previous = os.umask(0o117)
    try:
        with socketserver.UnixStreamServer(SOCKET, Handler) as server:
            # The API/Celery production image runs as UID 10001. No other
            # container on this private volume needs access to the RPC socket.
            os.chown(SOCKET, 10001, 10001)
            os.chmod(SOCKET, 0o600)
            server.serve_forever()
    finally:
        os.umask(previous)


if __name__ == "__main__":
    main()
