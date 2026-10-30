"""Bounded Unix-socket RPC to the dedicated privileged WireGuard controller."""
from __future__ import annotations

import asyncio
import json

from fastapi import HTTPException

from app.core.config import get_settings


async def configure_peer(*, public_key: str, ip: str, remove: bool = False) -> None:
    settings = get_settings()
    socket_path = settings.wireguard_control_socket
    token = settings.wireguard_control_token
    if not socket_path.startswith("/") or len(token) < 32:
        raise HTTPException(
            status_code=503, detail="WireGuard peer controller is not configured",
        )
    writer = None
    try:
        async with asyncio.timeout(12):
            reader, writer = await asyncio.open_unix_connection(socket_path)
            payload = {
                "token": token, "action": "remove" if remove else "install",
                "public_key": public_key, "ip": ip,
            }
            writer.write((json.dumps(payload) + "\n").encode("utf-8"))
            await writer.drain()
            raw = await reader.readline()
            if raw != b'{"ok": true}\n':
                raise ValueError("Controller did not acknowledge verified operation")
    except (OSError, TimeoutError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="WireGuard peer server did not confirm the operation",
        ) from exc
    finally:
        if writer is not None:
            writer.close()
            await writer.wait_closed()
