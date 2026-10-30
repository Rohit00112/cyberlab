"""Tests for the Docker provider (resource limits, PRD §44/§47)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.infrastructure import docker as docker_module
from app.infrastructure.base import LabProviderError
from app.infrastructure.docker import create_and_start_container


def _fake_requests(captured: dict):
    async def fake_request(method: str, path: str, body: dict | None = None):
        captured["method"] = method
        captured["path"] = path
        if "/containers/create" in path:
            captured["create_body"] = body
            return 201, b'{"Id":"abc123"}'
        if "/start" in path:
            return 204, b""
        if "/json" in path:
            payload = {
                "NetworkSettings": {
                    "Networks": {"net1": {"IPAddress": "172.30.0.10"}}
                }
            }
            return 200, json.dumps(payload).encode()
        return 404, b""

    return fake_request


async def test_container_create_applies_default_resource_limits(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(docker_module, "_request", _fake_requests(captured))

    container_id, ip = await create_and_start_container("c1", "alpine:3.20", "net1")

    assert container_id == "abc123"
    assert ip == "172.30.0.10"
    host_config = captured["create_body"]["HostConfig"]
    assert host_config["NetworkMode"] == "net1"
    assert host_config["NanoCpus"] > 0
    assert host_config["Memory"] > 0
    assert host_config["Memory"] == host_config["MemorySwap"]
    assert host_config["PidsLimit"] > 0


async def test_container_create_honours_explicit_limits(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(docker_module, "_request", _fake_requests(captured))

    await create_and_start_container(
        "c2",
        "alpine:3.20",
        "net1",
        cpu_limit=0.5,
        memory_limit_mb=128,
        pids_limit=64,
    )

    host_config = captured["create_body"]["HostConfig"]
    assert host_config["NanoCpus"] == 500_000_000
    assert host_config["Memory"] == 128 * 1024 * 1024
    assert host_config["PidsLimit"] == 64


async def test_docker_networks_are_internal_only(monkeypatch):
    requests = []

    async def fake_request(method, path, body=None):
        requests.append((method, path, body))
        if method == "GET":
            return 404, b""
        return 201, b"{}"

    monkeypatch.setattr(docker_module, "_request", fake_request)
    await docker_module.ensure_network("cyberlab-1234abcd")
    assert requests[-1][2] == {
        "Name": "cyberlab-1234abcd", "Driver": "bridge",
        "Internal": True, "CheckDuplicate": True,
    }

    async def external_network(method, path, body=None):
        return 200, b'{"Internal":false}'

    monkeypatch.setattr(docker_module, "_request", external_network)
    with pytest.raises(LabProviderError, match="not internal"):
        await docker_module.ensure_network("cyberlab-1234abcd")


def test_production_socket_does_not_fallback_to_unrestricted_host(monkeypatch):
    monkeypatch.setattr(
        docker_module, "get_settings",
        lambda: SimpleNamespace(
            lab_docker_socket="/run/cyberlab-docker-control/docker.sock",
            is_production=True,
        ),
    )
    monkeypatch.setattr(docker_module.os.path, "exists", lambda _: False)
    assert (
        docker_module._get_docker_socket()
        == "/run/cyberlab-docker-control/docker.sock"
    )
