"""Docker lab provider — thin async client for the Docker Engine API over unix socket.

Used by the lab service to provision isolated, per-user containers (Phase 2).
All orchestration happens server-side — students never get a Docker handle.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from app.core.config import get_settings
from app.infrastructure.base import LabProvider, LabProviderError


class DockerError(LabProviderError):
    """Raised when a Docker Engine operation fails."""


def _dechunk(body: bytes) -> bytes:
    out = bytearray()
    data = body
    while True:
        size_line, sep, rest = data.partition(b"\r\n")
        if not sep:
            break
        size = int(size_line.strip().split(b";")[0], 16)
        if size == 0:
            break
        out += rest[:size]
        data = rest[size:]
        if data.startswith(b"\r\n"):
            data = data[2:]
    return bytes(out)


def _parse_response(raw: bytes) -> tuple[int, bytes]:
    header, _, body = raw.partition(b"\r\n\r\n")
    lines = header.decode("utf-8", "replace").split("\r\n")
    status = int(lines[0].split(" ")[1])
    if any(h.lower().startswith("transfer-encoding:") and "chunked" in h.lower() for h in lines):
        body = _dechunk(body)
    return status, body


async def _request(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, bytes]:
    settings = get_settings()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(settings.lab_docker_socket), timeout=5
        )
    except (TimeoutError, OSError) as exc:
        raise DockerError(f"Docker socket unavailable: {exc}") from exc

    payload = "" if body is None else json.dumps(body)
    headers = (
        f"{method} {path} HTTP/1.1\r\n"
        "Host: docker\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload.encode('utf-8'))}\r\n"
        "Connection: close\r\n\r\n"
    )
    writer.write(headers.encode("utf-8") + payload.encode("utf-8"))
    await writer.drain()
    try:
        chunks = []
        while True:
            chunk = await asyncio.wait_for(reader.read(65536), timeout=30)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        writer.close()
        await writer.wait_closed()

    return _parse_response(b"".join(chunks))


def _ensure_status(status: int, ok: set[int], context: str) -> None:
    if status not in ok:
        raise DockerError(f"{context}: Docker Engine returned status {status}")


# ------ Standalone functions for backwards compat ------

async def docker_ping() -> bool:
    status, _ = await _request("GET", "/_ping")
    return status == 200


async def ensure_network(name: str) -> None:
    status, body = await _request("GET", f"/v1.24/networks/{name}")
    if status == 200:
        return
    status, _ = await _request(
        "POST", "/v1.24/networks/create", {"Name": name, "Driver": "bridge"}
    )
    if status not in (201, 409):
        raise DockerError(f"failed to create network {name}: status {status}")


async def create_and_start_container(
    name: str,
    image: str,
    network: str,
    cmd: list[str] | None = None,
    cpu_limit: float | None = None,
    memory_limit_mb: int | None = None,
    pids_limit: int | None = None,
) -> tuple[str, str]:
    """Create and start a container on the given network; return (id, ip).

    Resource limits default from settings (PRD §44/§47): a CPU cap (in cores),
    a memory cap (MB) and a process cap. All three are enforced by Docker.
    """
    settings = get_settings()
    host_config: dict[str, Any] = {"NetworkMode": network}
    if cpu_limit not in (None, 0):
        host_config["NanoCpus"] = int(cpu_limit * 1_000_000_000)
    if memory_limit_mb not in (None, 0):
        host_config["Memory"] = memory_limit_mb * 1024 * 1024
        host_config["MemorySwap"] = memory_limit_mb * 1024 * 1024
    if pids_limit not in (None, 0):
        host_config["PidsLimit"] = pids_limit
    if "NanoCpus" not in host_config and settings.lab_cpu_limit > 0:
        host_config["NanoCpus"] = int(settings.lab_cpu_limit * 1_000_000_000)
    if "Memory" not in host_config and settings.lab_memory_limit_mb > 0:
        memory = settings.lab_memory_limit_mb * 1024 * 1024
        host_config["Memory"] = host_config["MemorySwap"] = memory
    if "PidsLimit" not in host_config and settings.lab_pids_limit > 0:
        host_config["PidsLimit"] = settings.lab_pids_limit

    status, body = await _request(
        "POST",
        f"/v1.24/containers/create?name={name}",
        {
            "Image": image,
            "Cmd": cmd or ["sleep", "infinity"],
            "Tty": True,
            "AttachStdout": False,
            "HostConfig": host_config,
        },
    )
    _ensure_status(status, {201}, "container create")
    container_id = json.loads(body or b"{}").get("Id", "")

    status, _ = await _request(
        "POST", f"/v1.24/containers/{container_id}/start"
    )
    if status not in (204, 304):
        raise DockerError(f"container start failed: status {status}")

    ip = await inspect_ip(container_id, network)
    if not ip:
        raise DockerError(f"container {name} has no address on {network}")
    return container_id, ip


async def inspect_ip(container_id: str, network: str) -> str | None:
    status, body = await _request(
        "GET", f"/v1.24/containers/{container_id}/json"
    )
    if status != 200:
        return None
    data = json.loads(body or b"{}")
    networks = (data.get("NetworkSettings") or {}).get("Networks") or {}
    return (networks.get(network) or {}).get("IPAddress")


async def stop_container(container_id: str) -> None:
    status, _ = await _request(
        "POST", f"/v1.24/containers/{container_id}/stop?t=2"
    )
    if status not in (204, 304):
        raise DockerError(f"container stop failed: status {status}")


async def remove_container(container_id: str) -> None:
    status, _ = await _request(
        "DELETE", f"/v1.24/containers/{container_id}?force=1&v=1"
    )
    if status not in (204, 404):
        raise DockerError(f"container remove failed: status {status}")


async def container_status(container_id: str) -> dict[str, Any]:
    """Return container inspection data."""
    status, body = await _request(
        "GET", f"/v1.24/containers/{container_id}/json"
    )
    if status != 200:
        return {"error": f"inspect failed: status {status}"}
    data = json.loads(body or b"{}")
    state = data.get("State", {})
    return {
        "status": state.get("Status", "unknown"),
        "running": state.get("Running", False),
        "started_at": state.get("StartedAt"),
        "finished_at": state.get("FinishedAt"),
        "exit_code": state.get("ExitCode"),
        "pid": state.get("Pid"),
    }


async def container_logs(container_id: str, *, tail: int = 100) -> str:
    """Return recent container log output."""
    status, body = await _request(
        "GET", f"/v1.24/containers/{container_id}/logs?stdout=1&stderr=1&tail={tail}"
    )
    if status != 200:
        return f"[logs unavailable: status {status}]"
    return body.decode("utf-8", "replace")


# ------ Provider class ------

class DockerLabProvider(LabProvider):
    """LabProvider implementation backed by the Docker Engine API."""

    async def ping(self) -> bool:
        return await docker_ping()

    async def ensure_network(self, name: str) -> None:
        return await ensure_network(name)

    async def create_lab(
        self,
        name: str,
        image: str,
        network: str,
        *,
        cmd: list[str] | None = None,
        cpu_limit: float | None = None,
        memory_limit_mb: int | None = None,
        pids_limit: int | None = None,
    ) -> tuple[str, str]:
        kwargs: dict[str, Any] = {}
        if cmd is not None:
            kwargs["cmd"] = cmd
        if cpu_limit is not None:
            kwargs["cpu_limit"] = cpu_limit
        if memory_limit_mb is not None:
            kwargs["memory_limit_mb"] = memory_limit_mb
        if pids_limit is not None:
            kwargs["pids_limit"] = pids_limit
        return await create_and_start_container(name, image, network, **kwargs)

    async def stop_lab(self, provider_ref: str) -> None:
        return await stop_container(provider_ref)

    async def remove_lab(self, provider_ref: str) -> None:
        return await remove_container(provider_ref)

    async def inspect_ip(self, provider_ref: str, network: str) -> str | None:
        return await inspect_ip(provider_ref, network)

    async def lab_status(self, provider_ref: str) -> dict[str, Any]:
        return await container_status(provider_ref)

    async def lab_logs(self, provider_ref: str, *, tail: int = 100) -> str:
        return await container_logs(provider_ref, tail=tail)