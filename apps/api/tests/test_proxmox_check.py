"""Verify the live Proxmox readiness gate cannot mistake audit access for provisioning access."""
from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import unquote

import httpx
import pytest

from scripts import proxmox_check


@pytest.mark.asyncio
async def test_readiness_timeout_explains_unreachable_endpoint(monkeypatch, capsys):
    settings = SimpleNamespace(
        lab_provider="proxmox", proxmox_endpoint="https://proxmox.example.test",
        proxmox_node="com", proxmox_storage="local-lvm", proxmox_bridge="vmbr1",
        lab_image="9002", proxmox_user="test!token", proxmox_token_uuid="test-secret",
    )
    monkeypatch.setattr(proxmox_check, "get_settings", lambda: settings)
    checker = proxmox_check.ProxmoxCheck()

    async def timed_out(_path, request_timeout=10.0):
        raise httpx.ReadTimeout("")

    monkeypatch.setattr(checker, "_get", timed_out)
    assert await checker.run() == 1
    output = capsys.readouterr().out
    assert "[FAIL] auth" in output
    assert "ReadTimeout: request timed out" in output
    assert "network route" in output


@pytest.mark.asyncio
@pytest.mark.parametrize("grant_provisioning", [False, True])
async def test_readiness_checks_effective_token_privileges(
    monkeypatch, capsys, grant_provisioning
):
    settings = SimpleNamespace(
        lab_provider="proxmox",
        proxmox_endpoint="https://proxmox.example.test",
        proxmox_node="com",
        proxmox_storage="local-lvm",
        proxmox_bridge="vmbr0",
        lab_image="9000",
        proxmox_user="root@pam!cyberlab",
        proxmox_token_uuid="test-only-secret",
        proxmox_verify_ssl=True,
    )
    monkeypatch.setattr(proxmox_check, "get_settings", lambda: settings)
    checker = proxmox_check.ProxmoxCheck()
    required = {
        "/vms/9000": {"VM.Clone"},
        "/storage/local-lvm": {"Datastore.AllocateSpace"},
        "/vms/103": {
            "VM.Allocate", "VM.Config.CPU", "VM.Config.Memory",
            "VM.Config.Network", "VM.PowerMgmt", "VM.GuestAgent.Unrestricted",
        },
        "/sdn/zones/localnetwork/vmbr0": {"SDN.Use"},
        "/sdn/zones/localnetwork/vmbr1": {"SDN.Use"},
    }
    requested_paths = []

    async def get(path, request_timeout=10.0):
        if path.startswith("/access/permissions?path="):
            resource = unquote(path.split("=", 1)[1])
            requested_paths.append(resource)
            privileges = {"VM.Audit": 1}
            if grant_provisioning:
                privileges.update({privilege: 1 for privilege in required[resource]})
            payload = {resource: privileges}
        else:
            payload = {
                "/version": {"version": "9.2.5"},
                "/nodes": [{"node": "com", "status": "online"}],
                "/nodes/com/storage": [
                    {"storage": "local-lvm", "type": "lvmthin", "content": "images,rootdir"}
                ],
                "/nodes/com/network": [{"iface": "vmbr0", "type": "bridge"}],
                "/nodes/com/qemu": [
                    {"vmid": 9000, "name": "cyberlab-base", "template": 1, "status": "stopped"}
                ],
                "/nodes/com/qemu/9000/config": {
                    "net0": "virtio=02:00:00:00:00:01,bridge=vmbr1",
                },
                "/cluster/nextid": 103,
            }[path]
        return httpx.Response(
            200, json={"data": payload},
            request=httpx.Request("GET", "https://proxmox.example.test/api2/json"),
        )

    monkeypatch.setattr(checker, "_get", get)
    assert await checker.run() == (0 if grant_provisioning else 1)
    assert set(requested_paths) == set(required)
    output = capsys.readouterr().out
    if grant_provisioning:
        assert "proxmox: ready." in output
    else:
        assert "missing VM.Clone" in output
        assert "Datastore.AllocateSpace" in output
        assert "missing SDN.Use" in output
        assert "VM.GuestAgent.Unrestricted" in output
        assert "proxmox: not ready" in output


@pytest.mark.asyncio
async def test_malformed_permission_reply_fails_closed(monkeypatch):
    settings = SimpleNamespace(
        lab_provider="proxmox", proxmox_endpoint="https://proxmox.example.test",
        proxmox_node="com", proxmox_storage="local-lvm", proxmox_bridge="vmbr0",
        lab_image="9000", proxmox_user="test!token", proxmox_token_uuid="test-secret",
    )
    monkeypatch.setattr(proxmox_check, "get_settings", lambda: settings)
    checker = proxmox_check.ProxmoxCheck()

    async def get(_path, request_timeout=10.0):
        return httpx.Response(
            200, json={"data": {"/": {"VM.Clone": 1}}},
            request=httpx.Request("GET", "https://proxmox.example.test/api2/json"),
        )

    monkeypatch.setattr(checker, "_get", get)
    await checker._check_permissions("103")
    assert len(checker.results) == 4
    assert all(status == "fail" for status, _, _ in checker.results)


@pytest.mark.asyncio
async def test_live_smoke_never_deletes_an_unowned_vmid():
    from unittest.mock import AsyncMock

    from scripts.proxmox_smoke import _remove_owned_vm

    provider = SimpleNamespace(
        node="com",
        _request=AsyncMock(return_value=[{"vmid": 103, "name": "existing-vm"}]),
        remove_lab=AsyncMock(),
    )
    with pytest.raises(RuntimeError, match="refusing deletion"):
        await _remove_owned_vm(provider, "103", "cyberlab-smoke-test")
    provider.remove_lab.assert_not_awaited()


@pytest.mark.asyncio
async def test_live_smoke_removes_only_confirmed_owned_clone():
    from unittest.mock import AsyncMock

    from scripts.proxmox_smoke import _remove_owned_vm

    provider = SimpleNamespace(
        node="com",
        _request=AsyncMock(side_effect=[
            [{"vmid": 103, "name": "cyberlab-smoke-test"}],
            {"name": "cyberlab-smoke-test"},
            [],
        ]),
        remove_lab=AsyncMock(),
    )
    assert await _remove_owned_vm(provider, "103", "cyberlab-smoke-test")
    provider.remove_lab.assert_awaited_once_with("103")
