"""Fail-closed opt-in Proxmox SDN VNet staging support."""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import unquote

import httpx
import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.proxmox_sdn import parse_vnet_pool, validate_pool_subnet
from app.infrastructure import proxmox
from app.models.audit_logs import AuditLog
from app.models.proxmox_sdn_leases import ProxmoxSdnLease
from app.models.users import User
from app.services import labs
from scripts import proxmox_check, proxmox_smoke


def _sdn_settings(vnet: str = "clabnet1"):
    return get_settings().model_copy(update={"proxmox_sdn_vnet": vnet})


@pytest.mark.parametrize("raw", ["a", "a,a", "aa,", "../x,safe", "toolong99,safe"])
def test_sdn_pool_rejects_unsafe_or_duplicate_members(raw):
    with pytest.raises(ValueError, match="Proxmox SDN VNet pool"):
        parse_vnet_pool(raw)


def test_sdn_pool_preserves_operator_order():
    assert parse_vnet_pool(" clab001 , clab002 ") == ("clab001", "clab002")


def _subnet(cidr: str, gateway: str) -> list[dict]:
    prefix = gateway.rsplit(".", 1)[0]
    return [{
        "cidr": cidr,
        "gateway": gateway,
        "dhcp-range": [{
            "start-address": f"{prefix}.100", "end-address": f"{prefix}.199",
        }],
    }]


@pytest.mark.parametrize("subnets", [
    [],
    [{"cidr": "203.0.113.0/24", "gateway": "203.0.113.1",
      "dhcp-range": [{"start-address": "203.0.113.100", "end-address": "203.0.113.199"}]}],
    [{"cidr": "10.211.1.0/24", "gateway": "10.211.1.1", "snat": 1,
      "dhcp-range": [{"start-address": "10.211.1.100", "end-address": "10.211.1.199"}]}],
    [{"cidr": "10.211.1.0/24", "gateway": "10.211.1.1"}],
    [{"cidr": "10.211.1.0/24", "gateway": "10.211.1.1",
      "dhcp-range": [{"start-address": "10.211.1.1", "end-address": "10.211.1.199"}]}],
])
def test_sdn_pool_requires_private_routed_dhcp_and_no_snat(subnets):
    with pytest.raises(ValueError, match="SDN pool"):
        validate_pool_subnet(subnets)


def test_sdn_pool_accepts_valid_private_subnet():
    assert str(validate_pool_subnet(_subnet("10.211.1.0/24", "10.211.1.1"))) == (
        "10.211.1.0/24"
    )


@pytest.mark.asyncio
async def test_staging_pool_reservations_are_exclusive_and_never_auto_reused(monkeypatch):
    settings = _sdn_settings("").model_copy(update={
        "lab_provider": "proxmox", "proxmox_sdn_vnet_pool": "clab001,clab002",
    })
    monkeypatch.setattr(labs, "get_settings", lambda: settings)
    first, second, third = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    class FakeDB:
        def __init__(self):
            self.history = []
            self.leases = {}
            self.pending = []
            self.audits = []
            self.lock_calls = 0

        async def execute(self, stmt):
            if "pg_advisory_xact_lock" in str(stmt):
                self.lock_calls += 1
                return None
            if "FROM proxmox_sdn_leases" in str(stmt):
                rows = [(vnet, owner) for vnet, owner in self.leases.items()]
            else:
                rows = self.history
            return SimpleNamespace(all=lambda: list(rows))

        def add(self, lease):
            if isinstance(lease, ProxmoxSdnLease):
                self.pending.append(lease)
            else:
                self.audits.append(lease)

        async def flush(self):
            for lease in self.pending:
                self.leases[lease.vnet] = lease.user_id
            self.pending.clear()

    db = FakeDB()
    assert await labs._reserve_proxmox_sdn_vnet(db, first) == "clab001"
    assert db.leases == {"clab001": first}
    assert await labs._reserve_proxmox_sdn_vnet(db, second) == "clab002"
    assert await labs._reserve_proxmox_sdn_vnet(db, first) == "clab001"
    with pytest.raises(Exception, match="No unassigned staging SDN VNet"):
        await labs._reserve_proxmox_sdn_vnet(db, third)
    assert db.lock_calls == 4
    # Removing all lab history (including user deletion) does not free a lease.
    db.history.clear()
    assert db.leases == {"clab001": first, "clab002": second}
    assert [audit.event for audit in db.audits] == [
        "proxmox.sdn.reserve", "proxmox.sdn.reserve",
    ]
    db.history.append((third, "clab001"))
    with pytest.raises(Exception, match="Conflicting historical SDN"):
        await labs._reserve_proxmox_sdn_vnet(db, third)


@pytest.mark.asyncio
async def test_staging_pool_backfills_legacy_assignments(monkeypatch):
    settings = _sdn_settings("").model_copy(update={
        "lab_provider": "proxmox", "proxmox_sdn_vnet_pool": "clab001,clab002",
    })
    monkeypatch.setattr(labs, "get_settings", lambda: settings)
    previous, current = uuid.uuid4(), uuid.uuid4()

    class FakeDB:
        def __init__(self):
            self.staged = []

        async def execute(self, stmt):
            if "pg_advisory_xact_lock" in str(stmt):
                return None
            rows = [] if "FROM proxmox_sdn_leases" in str(stmt) else [
                (previous, "clab001"),
            ]
            return SimpleNamespace(all=lambda: rows)

        def add(self, lease):
            if isinstance(lease, ProxmoxSdnLease):
                self.staged.append((lease.vnet, lease.user_id))

        async def flush(self):
            pass

    db = FakeDB()
    assert await labs._reserve_proxmox_sdn_vnet(db, current) == "clab002"
    assert db.staged == [("clab001", previous), ("clab002", current)]


@pytest.mark.asyncio
async def test_staging_pool_postgres_lock_and_lease_survive_user_deletion(
    test_db, monkeypatch,
):
    settings = _sdn_settings("").model_copy(update={
        "lab_provider": "proxmox", "proxmox_sdn_vnet_pool": "clab001,clab002",
    })
    monkeypatch.setattr(labs, "get_settings", lambda: settings)
    users = [uuid.uuid4() for _ in range(3)]
    async with test_db() as db:
        for index in range(2):
            db.add(User(
                id=users[index], keycloak_sub=f"sdn-lease-user-{index}",
                display_name=f"SDN {index}",
            ))
        await db.commit()

    async def reserve(user_id):
        async with test_db() as db:
            name = await labs._reserve_proxmox_sdn_vnet(db, user_id)
            await db.commit()
            return name

    assigned = await asyncio.gather(reserve(users[0]), reserve(users[1]))
    assert set(assigned) == {"clab001", "clab002"}
    async with test_db() as db:
        owner_row = await db.get(User, users[0])
        await db.delete(owner_row)
        await db.commit()
        lease = await db.get(ProxmoxSdnLease, assigned[0])
        assert lease is not None and lease.user_id == users[0]
        assert (await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "proxmox.sdn.reserve",
        ))) == 2

    with pytest.raises(Exception, match="No unassigned staging SDN VNet"):
        await reserve(users[2])
    assert await reserve(users[0]) == assigned[0]


@pytest.mark.asyncio
async def test_pool_smoke_requires_explicit_approved_vnet(monkeypatch):
    settings = _sdn_settings("").model_copy(update={
        "lab_provider": "proxmox", "proxmox_sdn_vnet_pool": "clab001,clab002",
    })
    monkeypatch.setattr(proxmox_smoke, "get_settings", lambda: settings)
    monkeypatch.setattr(
        proxmox_smoke, "ProxmoxCheck",
        lambda: SimpleNamespace(run=AsyncMock(return_value=0)),
    )
    provider = SimpleNamespace(
        sdn_pool=("clab001", "clab002"), bridge="vmbr1",
        ensure_network=AsyncMock(side_effect=AssertionError("VM must not be allocated")),
    )
    monkeypatch.setattr(proxmox_smoke, "ProxmoxLabProvider", lambda: provider)
    assert await proxmox_smoke._run(True) == 2
    assert await proxmox_smoke._run(True, "clabnet1") == 2
    provider.ensure_network.assert_not_awaited()


@pytest.mark.asyncio
async def test_pool_smoke_clones_only_on_selected_vnet(monkeypatch):
    settings = _sdn_settings("").model_copy(update={
        "lab_provider": "proxmox", "proxmox_sdn_vnet_pool": "clab001,clab002",
        "lab_image": "9002",
    })
    monkeypatch.setattr(proxmox_smoke, "get_settings", lambda: settings)
    monkeypatch.setattr(
        proxmox_smoke, "ProxmoxCheck",
        lambda: SimpleNamespace(run=AsyncMock(return_value=0)),
    )

    async def request(method, path, **kwargs):
        if path.endswith("/nextid"):
            return 135
        if path.endswith("/qemu"):
            return []
        raise AssertionError(f"Unexpected API call: {method} {path}")

    provider = SimpleNamespace(
        sdn_pool=("clab001", "clab002"), bridge="vmbr1", node="com",
        _vmid=lambda vmid: str(vmid), _request=request,
        ensure_network=AsyncMock(),
        create_lab=AsyncMock(return_value=("135", "10.211.2.100")),
        lab_status=AsyncMock(return_value={"status": "running"}),
    )
    monkeypatch.setattr(proxmox_smoke, "ProxmoxLabProvider", lambda: provider)
    monkeypatch.setattr(proxmox_smoke, "_verify_flag", AsyncMock())
    monkeypatch.setattr(proxmox_smoke, "_remove_owned_vm", AsyncMock(return_value=True))
    assert await proxmox_smoke._run(True, "clab002") == 0
    provider.ensure_network.assert_awaited_once_with("clab002")
    assert provider.create_lab.await_args.args[2] == "clab002"


@pytest.mark.asyncio
async def test_staging_pool_only_attaches_approved_vnet(monkeypatch):
    settings = _sdn_settings("").model_copy(update={
        "proxmox_sdn_vnet_pool": "clab001,clab002",
    })
    monkeypatch.setattr(proxmox, "get_settings", lambda: settings)
    provider = proxmox.ProxmoxLabProvider()
    provider._require_sdn_vnet = AsyncMock()
    provider._wait_for_ip = AsyncMock(return_value="10.211.1.100")
    request = AsyncMock()
    monkeypatch.setattr(provider, "_request", request)

    with pytest.raises(proxmox.ProxmoxError, match="approved pool"):
        await provider.create_lab("test", "9002", "clabnet1")
    request.assert_not_awaited()

    async def api(method, path, **kwargs):
        if path.endswith("/cluster/nextid"):
            return 135
        if path.endswith("/qemu"):
            return [{"vmid": 9002, "template": 1}]
        if path.endswith("/storage/local-lvm/status"):
            return {"active": 1, "content": "images"}
        if "/tasks/" in path:
            return {"status": "stopped", "exitstatus": "OK"}
        if path.endswith("/clone") or path.endswith("/status/start"):
            return "UPID:pve:00000001:00000002:00000003:qmclone:135:root@pam:"
        if method == "PUT" and path.endswith("/135/config"):
            assert kwargs["json_data"]["net0"] == "virtio,bridge=clab002"
            return {}
        raise AssertionError(f"Unexpected Proxmox request {method} {path}")

    monkeypatch.setattr(provider, "_request", api)
    assert await provider.create_lab("test", "9002", "clab002") == (
        "135", "10.211.1.100",
    )
    provider._require_sdn_vnet.assert_awaited_once_with("clab002")


@pytest.mark.asyncio
async def test_staging_pool_readiness_checks_every_bridge_and_acl(monkeypatch, capsys):
    settings = _sdn_settings("").model_copy(update={
        "lab_provider": "proxmox", "proxmox_sdn_vnet_pool": "clab001,clab002",
        "lab_image": "9002", "proxmox_bridge": "vmbr1",
    })
    monkeypatch.setattr(proxmox_check, "get_settings", lambda: settings)
    checker = proxmox_check.ProxmoxCheck()
    acl_paths = []

    async def get(path, request_timeout=10.0):
        if path.startswith("/access/permissions?path="):
            resource = unquote(path.split("=", 1)[1])
            acl_paths.append(resource)
            grants = {
                "/vms/9002": ["VM.Clone"],
                "/storage/local-lvm": ["Datastore.AllocateSpace"],
                "/vms/103": ["VM.Allocate", "VM.Config.CPU", "VM.Config.Memory",
                              "VM.Config.Network", "VM.PowerMgmt", "VM.GuestAgent.Unrestricted"],
                "/sdn/zones/localnetwork/vmbr1": ["SDN.Use"],
                "/sdn/zones/clabzone/clab001": ["SDN.Use"],
                "/sdn/zones/clabzone/clab002": ["SDN.Use"],
            }
            data = {resource: {grant: 1 for grant in grants[resource]}}
        elif path.startswith("/cluster/sdn/vnets/clab"):
            if path.endswith("/subnets"):
                vnet_id = path.split("/")[-2]
                index = 1 if vnet_id == "clab001" else 2
                data = _subnet(f"10.211.{index}.0/24", f"10.211.{index}.1")
            else:
                data = {"vnet": path.rsplit("/", 1)[1], "zone": "clabzone"}
        elif path.endswith("/sdn/zones/clabzone/bridges"):
            data = [{"name": "clab001"}, {"name": "clab002"}]
        else:
            data = {
                "/version": {"version": "9.2.5"},
                "/nodes": [{"node": settings.proxmox_node, "status": "online"}],
                f"/nodes/{settings.proxmox_node}/storage": [{
                    "storage": "local-lvm", "type": "lvmthin", "content": "images",
                }],
                f"/nodes/{settings.proxmox_node}/sdn/zones": [{
                    "zone": "clabzone", "status": "available",
                }],
                f"/nodes/{settings.proxmox_node}/qemu": [{
                    "vmid": 9002, "template": 1, "name": "cyberlab-base", "status": "stopped",
                }],
                f"/nodes/{settings.proxmox_node}/qemu/9002/config": {
                    "net0": "virtio,bridge=vmbr1",
                },
                "/cluster/nextid": 103,
            }[path]
        return httpx.Response(200, json={"data": data}, request=httpx.Request(
            "GET", "https://pve.example.test/api2/json",
        ))

    monkeypatch.setattr(checker, "_get", get)
    assert await checker.run() == 0
    assert "/sdn/zones/clabzone/clab001" in acl_paths
    assert "/sdn/zones/clabzone/clab002" in acl_paths
    assert "proxmox: ready." in capsys.readouterr().out


@pytest.mark.asyncio
async def test_sdn_staging_vnet_must_exist_and_be_applied(monkeypatch):
    monkeypatch.setattr(proxmox, "get_settings", _sdn_settings)
    provider = proxmox.ProxmoxLabProvider()
    paths = []

    async def request(method, path, **_kwargs):
        paths.append(path)
        if path.endswith("/sdn/vnets/clabnet1"):
            return {"vnet": "clabnet1", "zone": "clabzone"}
        if path.endswith("/sdn/zones"):
            return [{"zone": "clabzone", "status": "available"}]
        if path.endswith("/sdn/zones/clabzone/bridges"):
            return [{"name": "clabnet1", "ports": []}]
        raise AssertionError("Unexpected API request before network preflight")

    monkeypatch.setattr(provider, "_request", request)
    await provider.ensure_network("ignored-docker-network")
    assert paths == [
        "/api2/json/cluster/sdn/vnets/clabnet1",
        f"/api2/json/nodes/{provider.node}/sdn/zones",
        f"/api2/json/nodes/{provider.node}/sdn/zones/clabzone/bridges",
    ]

    async def missing_vnet(_method, path, **_kwargs):
        if path.endswith("/sdn/vnets/clabnet1"):
            return {"vnet": "clabnet1", "zone": ""}
        raise AssertionError("No VM allocation is permitted")

    monkeypatch.setattr(provider, "_request", missing_vnet)
    with pytest.raises(proxmox.ProxmoxError, match="not configured and applied"):
        await provider.create_lab("test", "9002", "ignored")

    async def unapplied_vnet(_method, path, **_kwargs):
        if path.endswith("/sdn/vnets/clabnet1"):
            return {"vnet": "clabnet1", "zone": "clabzone"}
        if path.endswith("/sdn/zones"):
            return [{"zone": "clabzone", "status": "available"}]
        if path.endswith("/sdn/zones/clabzone/bridges"):
            return []
        raise AssertionError("No VM allocation is permitted")

    monkeypatch.setattr(provider, "_request", unapplied_vnet)
    with pytest.raises(proxmox.ProxmoxError, match="not configured and applied"):
        await provider.create_lab("test", "9002", "ignored")


@pytest.mark.asyncio
async def test_sdn_staging_vnet_is_used_for_guest_nic(monkeypatch):
    monkeypatch.setattr(proxmox, "get_settings", _sdn_settings)
    provider = proxmox.ProxmoxLabProvider()
    provider._require_sdn_vnet = AsyncMock()
    provider._wait_for_ip = AsyncMock(return_value="10.210.0.100")
    upid = "UPID:pve:00000001:00000002:00000003:qmclone:135:root@pam:"
    configured = []

    async def request(method, path, **kwargs):
        if path.endswith("/cluster/nextid"):
            return 135
        if path == f"/api2/json/nodes/{provider.node}/qemu":
            return [{"vmid": 9002, "template": 1}]
        if path.endswith("/storage/local-lvm/status"):
            return {"active": 1, "content": "images,rootdir"}
        if path.endswith("/9002/clone") or path.endswith("/135/status/start"):
            return upid
        if "/tasks/" in path:
            return {"status": "stopped", "exitstatus": "OK"}
        if path.endswith("/135/config") and method == "PUT":
            configured.append(kwargs["json_data"])
            return None
        raise AssertionError(f"Unexpected Proxmox call {method} {path}")

    monkeypatch.setattr(provider, "_request", request)
    assert await provider.create_lab("test", "9002", "ignored") == (
        "135", "10.210.0.100",
    )
    provider._require_sdn_vnet.assert_awaited_once()
    assert configured == [{"net0": "virtio,bridge=clabnet1"}]


@pytest.mark.parametrize("vnet", ["../clab", "!invalid", "a" * 9])
def test_sdn_staging_vnet_name_rejects_path_injection(monkeypatch, vnet):
    monkeypatch.setattr(proxmox, "get_settings", lambda: _sdn_settings(vnet))
    with pytest.raises(proxmox.ProxmoxError, match="Invalid Proxmox SDN VNet"):
        proxmox.ProxmoxLabProvider()


def test_proxmox_shared_network_is_rejected_in_production(monkeypatch):
    settings = _sdn_settings().model_copy(update={
        "environment": "production",
        "proxmox_user": "operator@pve!cyberlab",
        "proxmox_token_uuid": "fake-token",
        "proxmox_verify_ssl": True,
    })
    monkeypatch.setattr(proxmox, "get_settings", lambda: settings)
    with pytest.raises(proxmox.ProxmoxError, match="per-student SDN isolation"):
        proxmox.ProxmoxLabProvider()


@pytest.mark.asyncio
async def test_readiness_must_not_claim_production_is_safe(monkeypatch, capsys):
    settings = _sdn_settings().model_copy(update={
        "environment": "production", "lab_provider": "proxmox",
    })
    monkeypatch.setattr(proxmox_check, "get_settings", lambda: settings)
    checker = proxmox_check.ProxmoxCheck()
    request = AsyncMock(side_effect=AssertionError("Must not contact Proxmox"))
    monkeypatch.setattr(checker, "_get", request)
    assert await checker.run() == 1
    assert "per-user SDN and VPN/firewall" in capsys.readouterr().out
    request.assert_not_awaited()


@pytest.mark.asyncio
async def test_proxmox_lab_hint_does_not_claim_per_user_isolation(monkeypatch):
    settings = _sdn_settings().model_copy(update={"lab_provider": "proxmox"})
    monkeypatch.setattr(labs, "get_settings", lambda: settings)
    fake_provider = SimpleNamespace(
        create_lab=AsyncMock(return_value=("135", "10.210.0.100"))
    )
    monkeypatch.setattr(labs, "get_lab_provider", lambda: fake_provider)
    lab = SimpleNamespace(
        id=uuid.uuid4(), user_id=uuid.uuid4(), container_name="",
        network_name="cyberlab-abcdefgh", provider=None, provider_ref=None,
        container_id=None, flag_hash=None, flag_path=None, connection_hint=None,
    )
    await labs._start_container(lab, {
        "image": "9002", "flag_path": "/flag.txt", "expiry_minutes": 30,
    })
    assert "shared Proxmox network clabnet1" in lab.connection_hint
    assert "not approved for multi-student access" in lab.connection_hint
    assert "isolated network cyberlab-abcdefgh" not in lab.connection_hint
    assert lab.provider_ref == "135"


@pytest.mark.asyncio
async def test_readiness_uses_sdn_zone_permissions(monkeypatch, capsys):
    settings = SimpleNamespace(
        lab_provider="proxmox", proxmox_endpoint="https://pve.example.test",
        proxmox_node="com", proxmox_storage="local-lvm",
        proxmox_bridge="vmbr1", proxmox_sdn_vnet="clabnet1",
        proxmox_user="test!token", proxmox_token_uuid="test-secret",
        lab_image="9002",
    )
    monkeypatch.setattr(proxmox_check, "get_settings", lambda: settings)
    checker = proxmox_check.ProxmoxCheck()
    requested_acl_paths = []

    async def get(path, request_timeout=10.0):
        if path.startswith("/access/permissions?path="):
            resource = unquote(path.split("=", 1)[1])
            requested_acl_paths.append(resource)
            required = {
                "/vms/9002": ["VM.Clone"],
                "/storage/local-lvm": ["Datastore.AllocateSpace"],
                "/vms/103": ["VM.Allocate", "VM.Config.CPU", "VM.Config.Memory",
                              "VM.Config.Network", "VM.PowerMgmt", "VM.GuestAgent.Unrestricted"],
                "/sdn/zones/localnetwork/vmbr1": ["SDN.Use"],
                "/sdn/zones/clabzone/clabnet1": ["SDN.Use"],
            }
            data = {resource: {grant: 1 for grant in required[resource]}}
        else:
            data = {
                "/version": {"version": "9.2.5"},
                "/nodes": [{"node": "com", "status": "online"}],
                "/nodes/com/storage": [{"storage": "local-lvm", "type": "lvmthin",
                                        "content": "images,rootdir"}],
                "/cluster/sdn/vnets/clabnet1": {"vnet": "clabnet1", "zone": "clabzone"},
                "/nodes/com/sdn/zones": [{"zone": "clabzone", "status": "available"}],
                "/nodes/com/sdn/zones/clabzone/bridges": [{"name": "clabnet1", "ports": []}],
                "/nodes/com/qemu": [{"vmid": 9002, "name": "cyberlab-base",
                                     "template": 1, "status": "stopped"}],
                "/nodes/com/qemu/9002/config": {"net0": "virtio,bridge=vmbr1"},
                "/cluster/nextid": 103,
            }[path]
        return httpx.Response(
            200, json={"data": data},
            request=httpx.Request("GET", "https://pve.example.test/api2/json"),
        )

    monkeypatch.setattr(checker, "_get", get)
    assert await checker.run() == 0
    assert "/sdn/zones/clabzone/clabnet1" in requested_acl_paths
    assert "/sdn/zones/localnetwork/vmbr1" in requested_acl_paths
    assert "proxmox: ready." in capsys.readouterr().out
