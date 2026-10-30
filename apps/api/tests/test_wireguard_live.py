"""Isolated WireGuard RPC and database lifecycle tests; no host wg access."""
from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.api.deps import CurrentUser
from app.infrastructure import wireguard
from app.models.audit_logs import AuditLog
from app.models.users import User
from app.models.vpn_scoring import VPNPeer
from app.services import vpn

ROOT = Path(__file__).resolve().parents[3]
CONTROLLER = ROOT / "apps/wireguard-controller/controller.py"
KEY = base64.b64encode(bytes(range(32))).decode("ascii")
TOKEN = "integration-only-" + "a" * 48


def settings():
    return SimpleNamespace(
        is_production=True,
        wireguard_control_socket="/run/cyberlab-wireguard/control.sock",
        wireguard_control_token=TOKEN,
        wireguard_server_public_key=KEY,
        wireguard_endpoint="vpn.example.org:51820",
    )


def controller_module():
    spec = importlib.util.spec_from_file_location("wg_controller_tests", CONTROLLER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_restricted_wireguard_controller_checks_and_verifies_peer(monkeypatch):
    controller = controller_module()
    monkeypatch.setattr(controller, "TOKEN", TOKEN)
    routes = {}
    commands = []

    def invoke(*args):
        commands.append(args)
        if args[:2] == ("show", "wg0"):
            return "\n".join(f"{k} {v}" for k, v in routes.items())
        if args[0] == "set":
            if args[-1] == "remove":
                routes.pop(args[3], None)
            else:
                routes[args[3]] = args[-1]
            return ""
        raise AssertionError(args)

    monkeypatch.setattr(controller, "invoke", invoke)
    request = {"token": TOKEN, "action": "install",
               "public_key": KEY, "ip": "10.200.0.2"}
    controller.perform(request)
    assert routes[KEY] == "10.200.0.2/32"
    controller.perform({**request, "action": "remove"})
    assert KEY not in routes
    assert any(command[0] == "set" for command in commands)
    for invalid in [
        {**request, "token": "wrong"},
        {**request, "ip": "192.168.1.10"},
        {**request, "public_key": "invalid"},
        {**request, "action": "execute"},
        {**request, "command": "/bin/sh"},
    ]:
        with pytest.raises(ValueError):
            controller.perform(invalid)


@pytest.mark.asyncio
async def test_wireguard_client_acknowledgement_is_required(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="cyberlab-wg-", dir="/tmp") as folder:
        socket_path = Path(folder) / "wg.sock"
        configured = settings()
        configured.wireguard_control_socket = str(socket_path)
        monkeypatch.setattr(wireguard, "get_settings", lambda: configured)
        seen = []

        async def handle(reader, writer):
            request = json.loads(await reader.readline())
            seen.append(request)
            writer.write(b'{"ok": true}\n')
            await writer.drain()
            writer.close()

        server = await asyncio.start_unix_server(handle, path=str(socket_path))
        try:
            await wireguard.configure_peer(public_key=KEY, ip="10.200.0.2")
        finally:
            server.close()
            await server.wait_closed()
        with pytest.raises(HTTPException) as exc:
            await wireguard.configure_peer(
                public_key=KEY, ip="10.200.0.2", remove=True,
            )
    assert seen[0] == {
        "token": TOKEN, "action": "install",
        "public_key": KEY, "ip": "10.200.0.2",
    }
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_production_peer_installation_and_revocation_are_verified(
    test_db, monkeypatch,
):
    monkeypatch.setattr(vpn, "get_settings", settings)
    server = AsyncMock()
    monkeypatch.setattr(vpn, "configure_peer", server)
    async with test_db() as db:
        user_row = User(keycloak_sub="wg-live-student", display_name="WG Student")
        db.add(user_row)
        await db.commit()
        user = CurrentUser(
            id=user_row.id, keycloak_sub=user_row.keycloak_sub,
            roles=["student"], permissions=["challenge.view"],
        )
        peer, private = await vpn.get_or_create_vpn_peer(
            db, user, client_public_key=KEY,
        )
        assert private is None and peer.public_key == KEY
        server.assert_awaited_with(public_key=KEY, ip=peer.allocated_ip)
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "vpn.peer_create",
        )) == 1
        existing, _ = await vpn.get_or_create_vpn_peer(db, user, client_public_key=KEY)
        assert existing.id == peer.id
        assert await vpn.get_active_vpn_peer(db, user) is not None
        await vpn.revoke_vpn_peer(db, user)
        assert (await db.get(VPNPeer, peer.id)).is_active is False
        server.assert_awaited_with(
            public_key=KEY, ip=peer.allocated_ip, remove=True,
        )
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "vpn.peer_revoke",
        )) == 1


@pytest.mark.asyncio
async def test_failed_server_installation_does_not_register_peer(test_db, monkeypatch):
    monkeypatch.setattr(vpn, "get_settings", settings)
    monkeypatch.setattr(vpn, "configure_peer", AsyncMock(side_effect=HTTPException(
        status_code=503, detail="unreachable",
    )))
    async with test_db() as db:
        row = User(keycloak_sub="wg-denied", display_name="WG Denied")
        db.add(row)
        await db.commit()
        user = CurrentUser(
            id=row.id, keycloak_sub=row.keycloak_sub,
            roles=["student"], permissions=["challenge.view"],
        )
        with pytest.raises(HTTPException) as exc:
            await vpn.get_or_create_vpn_peer(db, user, client_public_key=KEY)
        assert exc.value.status_code == 503
        await db.rollback()
        assert await db.scalar(select(func.count()).select_from(VPNPeer)) == 0


@pytest.mark.asyncio
async def test_expired_wireguard_peers_are_revoked_by_maintenance(test_db, monkeypatch):
    monkeypatch.setattr(vpn, "get_settings", settings)
    server = AsyncMock()
    monkeypatch.setattr(vpn, "configure_peer", server)
    async with test_db() as db:
        row = User(keycloak_sub="wg-expired", display_name="Expired WG")
        db.add(row)
        await db.flush()
        peer = VPNPeer(
            user_id=row.id, public_key=KEY, allocated_ip="10.200.0.2",
            is_active=True, expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        db.add(peer)
        await db.commit()
        assert await vpn.reconcile_wireguard_server_peers(db) == 1
        server.assert_awaited_with(
            public_key=KEY, ip="10.200.0.2", remove=True,
        )
        assert (await db.get(VPNPeer, peer.id)).is_active is False
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "vpn.peer_expire",
        )) == 1
