"""Unix-socket Docker Engine gate for the CyberLab lab provider.

Only the operations used by the lab adapter are forwarded. This service is
the *only* production container with the host Docker socket mounted. It has
no published port or network access; the API/worker share only its socket.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ENGINE_SOCKET = os.getenv("DOCKER_ENGINE_SOCKET", "/var/run/docker.sock")
CONTROL_SOCKET = os.getenv(
    "DOCKER_CONTROL_SOCKET", "/run/cyberlab-docker-control/docker.sock"
)
MAX_BODY = 65536
NETWORK = re.compile(r"cyberlab-[0-9a-f]{8}\Z")
CONTAINER = re.compile(r"[0-9a-f]{64}\Z")
LAB_NAME = re.compile(r"lab-[0-9a-f]{8}-[0-9a-f]{8}\Z")


class Denied(ValueError):
    """The requested Docker operation is outside the lab allowlist."""


def _network(value: object) -> bool:
    return isinstance(value, str) and NETWORK.fullmatch(value) is not None


def _resource_limit(value: object, maximum: int) -> bool:
    return type(value) is int and 0 < value <= maximum


def authorize(method: str, target: str, payload: bytes) -> None:
    """Validate a single canonical Engine request, including create options."""
    if not target.startswith("/") or "%" in target or "//" in target:
        raise Denied("invalid request path")
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise Denied("invalid request target")
    path, query = parsed.path, parse_qs(parsed.query, keep_blank_values=True)
    if method == "GET" and path == "/_ping" and not query and not payload:
        return
    if method == "GET" and path.startswith("/v1.24/networks/"):
        if not query and not payload and _network(path.removeprefix("/v1.24/networks/")):
            return
    if method == "POST" and path == "/v1.24/networks/create" and not query:
        try:
            data = json.loads(payload)
        except (UnicodeDecodeError, ValueError) as exc:
            raise Denied("invalid network request") from exc
        if (
            isinstance(data, dict)
            and set(data) == {"Name", "Driver", "Internal", "CheckDuplicate"}
            and _network(data["Name"])
            and data["Driver"] == "bridge"
            and data["Internal"] is True
            and data["CheckDuplicate"] is True
        ):
            return
        raise Denied("network requires an internal CyberLab bridge")
    if method == "POST" and path == "/v1.24/containers/create":
        if set(query) != {"name"} or len(query["name"]) != 1 or not LAB_NAME.fullmatch(query["name"][0]):
            raise Denied("invalid lab name")
        try:
            data = json.loads(payload)
        except (UnicodeDecodeError, ValueError) as exc:
            raise Denied("invalid container request") from exc
        if not isinstance(data, dict) or set(data) != {
            "Image", "Cmd", "Tty", "AttachStdout", "HostConfig"
        }:
            raise Denied("unrecognized container options")
        host = data["HostConfig"]
        if (
            not isinstance(data["Image"], str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/@:-]{0,254}", data["Image"])
            or not isinstance(data["Cmd"], list)
            or not 1 <= len(data["Cmd"]) <= 16
            or not all(isinstance(v, str) and len(v) <= 8192 for v in data["Cmd"])
            or data["Tty"] is not True
            or data["AttachStdout"] is not False
            or not isinstance(host, dict)
            or not _network(host.get("NetworkMode"))
            or set(host) - {"NetworkMode", "NanoCpus", "Memory", "MemorySwap", "PidsLimit"}
        ):
            raise Denied("unsafe container options")
        limits = {
            "NanoCpus": 16_000_000_000,
            "Memory": 32 * 1024**3,
            "MemorySwap": 32 * 1024**3,
            "PidsLimit": 2048,
        }
        if any(
            not _resource_limit(host[key], maximum)
            for key, maximum in limits.items() if key in host
        ):
            raise Denied("invalid container resource limit")
        if "MemorySwap" in host and host.get("Memory") != host["MemorySwap"]:
            raise Denied("memory swap must match memory cap")
        return
    match = re.fullmatch(r"/v1\.24/containers/([0-9a-f]{64})/(start|stop|json|logs)", path)
    if match and CONTAINER.fullmatch(match[1]) and not payload:
        operation = match[2]
        if (
            (method, operation) in {("POST", "start"), ("GET", "json")}
            and not query
        ) or (method, operation) == ("POST", "stop") and query == {"t": ["2"]}:
            return
        if (method, operation) == ("GET", "logs"):
            if (
                set(query) == {"stdout", "stderr", "tail"}
                and query["stdout"] == ["1"]
                and query["stderr"] == ["1"]
                and len(query["tail"]) == 1
                and query["tail"][0].isdigit()
                and 0 <= int(query["tail"][0]) <= 5000
            ):
                return
    if method == "DELETE" and not payload and query == {"force": ["1"], "v": ["1"]}:
        ref = path.removeprefix("/v1.24/containers/")
        if path.startswith("/v1.24/containers/") and CONTAINER.fullmatch(ref):
            return
    raise Denied("Docker operation is not permitted")


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    upstream_writer = None
    try:
        raw_header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        if len(raw_header) > 8192:
            raise Denied("oversized HTTP headers")
        lines = raw_header[:-4].decode("ascii").split("\r\n")
        method, target, version = lines[0].split(" ")
        if version != "HTTP/1.1" or method not in {"GET", "POST", "DELETE"}:
            raise Denied("unsupported request")
        headers = {}
        for line in lines[1:]:
            key, separator, value = line.partition(":")
            if not separator or key.lower() in headers:
                raise Denied("invalid HTTP headers")
            headers[key.lower()] = value.strip()
        if "transfer-encoding" in headers:
            raise Denied("chunked request bodies are not allowed")
        length_text = headers.get("content-length", "0")
        if not length_text.isdecimal() or int(length_text) > MAX_BODY:
            raise Denied("invalid request body length")
        payload = await asyncio.wait_for(reader.readexactly(int(length_text)), 10)
        authorize(method, target, payload)
        upstream_reader, upstream_writer = await asyncio.wait_for(
            asyncio.open_unix_connection(ENGINE_SOCKET), 5
        )
        request = (
            f"{method} {target} HTTP/1.1\r\nHost: docker\r\n"
            f"Content-Length: {len(payload)}\r\nContent-Type: application/json\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        upstream_writer.write(request + payload)
        await upstream_writer.drain()
        while chunk := await asyncio.wait_for(upstream_reader.read(65536), 30):
            writer.write(chunk)
            await writer.drain()
    except (Denied, ValueError, UnicodeError) as exc:
        _reject(writer, 403, str(exc))
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError, OSError):
        _reject(writer, 502, "Docker controller request failed")
    finally:
        if upstream_writer is not None:
            upstream_writer.close()
            try:
                await upstream_writer.wait_closed()
            except (ConnectionResetError, BrokenPipeError):
                pass
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionResetError, BrokenPipeError):
            # A health probe may close immediately after reading HTTP status.
            pass


def _reject(writer: asyncio.StreamWriter, code: int, message: str) -> None:
    body = json.dumps({"message": message}).encode("utf-8")
    writer.write(
        f"HTTP/1.1 {code} Denied\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode("ascii") + body
    )


async def main() -> None:
    path = Path(CONTROL_SOCKET)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        # A stopped container can leave a Unix socket inode in the named volume.
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(path)), 1
            )
        except (OSError, TimeoutError):
            path.unlink()
        else:
            writer.close()
            await writer.wait_closed()
            raise RuntimeError("another Docker controller is using the socket")
    server = await asyncio.start_unix_server(_handle, str(path))
    os.chmod(path, 0o666)  # Only services mounting this volume can reach the socket.
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
