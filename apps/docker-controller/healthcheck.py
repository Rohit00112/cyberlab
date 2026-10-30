"""Require the restricted controller to be able to reach Docker itself."""

import os
import socket
import sys

path = os.getenv(
    "DOCKER_CONTROL_SOCKET", "/run/cyberlab-docker-control/docker.sock"
)
try:
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(2)
        client.connect(path)
        client.sendall(b"GET /_ping HTTP/1.1\r\nHost: docker\r\n\r\n")
        response = client.recv(64)
    if not response.startswith(b"HTTP/1.1 200 "):
        raise RuntimeError("Docker Engine did not respond successfully")
except (OSError, RuntimeError) as exc:
    print(f"Docker controller not ready: {type(exc).__name__}", file=sys.stderr)
    raise SystemExit(1) from exc
