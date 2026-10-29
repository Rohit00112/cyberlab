"""WireGuard development preview; no server-side peer provisioning is implemented."""

from __future__ import annotations

import base64
import ipaddress
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric import x25519
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.models.vpn_scoring import VPNPeer
from app.schemas.vpn import VPNConfigOut, VPNPeerOut
from app.services.users import record_audit

# Default WireGuard subnet parameters
VPN_SUBNET_PREFIX = "10.200.0"


def _require_vpn_preview() -> None:
    """Never represent database-only registrations as live production VPN peers."""
    if get_settings().is_production:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WireGuard server peer provisioning/revocation is unavailable in production.",
        )


def _validated_public_key(value: str, *, client: bool) -> str:
    """Require a canonical 32-byte WireGuard public key, without whitespace."""
    invalid_status = (
        status.HTTP_422_UNPROCESSABLE_ENTITY if client else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    label = "client" if client else "server"
    try:
        if not value or any(char.isspace() for char in value):
            raise ValueError("missing or whitespace-containing key")
        raw = base64.b64decode(value, validate=True)
        if len(raw) != 32 or raw == bytes(32) or base64.b64encode(raw).decode("ascii") != value:
            raise ValueError("invalid public key")
    except (ValueError, UnicodeEncodeError) as exc:
        raise HTTPException(
            status_code=invalid_status, detail=f"Invalid WireGuard {label} public key"
        ) from exc
    return value


def _validated_endpoint(value: str) -> str:
    """Accept only a WireGuard hostname/IPv4/[IPv6]:port endpoint."""
    try:
        if not value or any(char.isspace() for char in value):
            raise ValueError("missing or whitespace-containing endpoint")
        parsed = urlsplit(f"wg://{value}")
        hostname, port = parsed.hostname, parsed.port
        if (
            not hostname
            or not port
            or parsed.netloc != value
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("invalid endpoint structure")
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            # Require DNS labels (including localhost for local development).
            labels = hostname.split(".")
            if len(hostname) > 253 or any(
                not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
                for label in labels
            ):
                raise ValueError("invalid endpoint hostname") from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Invalid or missing WireGuard server endpoint",
        ) from exc
    return value


def _validated_server_settings() -> tuple[str, str]:
    settings = get_settings()
    return (
        _validated_endpoint(settings.wireguard_endpoint),
        _validated_public_key(settings.wireguard_server_public_key, client=False),
    )


def generate_wireguard_keypair() -> tuple[str, str]:
    """Generate a standard Curve25519 (X25519) WireGuard keypair."""
    priv = x25519.X25519PrivateKey.generate()
    priv_bytes = priv.private_bytes_raw()
    pub_bytes = priv.public_key().public_bytes_raw()
    return base64.b64encode(priv_bytes).decode("ascii"), base64.b64encode(pub_bytes).decode("ascii")


async def _allocate_next_peer_ip(db: AsyncSession) -> str:
    """Find the next available IP address in the VPN subnet pool (10.200.0.2 - 10.200.0.254)."""
    assigned_ips = set((await db.scalars(select(VPNPeer.allocated_ip))).all())
    for host_num in range(2, 255):
        candidate = f"{VPN_SUBNET_PREFIX}.{host_num}"
        if candidate not in assigned_ips:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="VPN address pool exhausted. Please contact platform administrators.",
    )


def _peer_to_out(peer: VPNPeer) -> VPNPeerOut:
    return VPNPeerOut(
        id=peer.id,
        user_id=peer.user_id,
        public_key=peer.public_key,
        allocated_ip=peer.allocated_ip,
        is_active=peer.is_active,
        allowed_subnets=peer.allowed_subnets,
        expires_at=peer.expires_at,
        created_at=peer.created_at,
    )


async def get_or_create_vpn_peer(
    db: AsyncSession,
    user: CurrentUser,
    client_public_key: str | None = None,
) -> tuple[VPNPeer, str | None]:
    """Retrieve or record a development peer (not installed on a VPN server).

    Returns (VPNPeer, client_private_key_if_generated).
    """
    _require_vpn_preview()
    validated_client_key = (
        _validated_public_key(client_public_key, client=True)
        if client_public_key is not None
        else None
    )
    peer = (
        await db.scalars(
            select(VPNPeer).where(VPNPeer.user_id == user.id, VPNPeer.is_active.is_(True))
        )
    ).first()

    generated_priv_key: str | None = None

    if not peer:
        if validated_client_key is not None:
            pub_key = validated_client_key
        else:
            generated_priv_key, pub_key = generate_wireguard_keypair()

        allocated_ip = await _allocate_next_peer_ip(db)
        peer = VPNPeer(
            user_id=user.id,
            public_key=pub_key,
            allocated_ip=allocated_ip,
            is_active=True,
            allowed_subnets=["10.100.0.0/16", f"{VPN_SUBNET_PREFIX}.0/24"],
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        db.add(peer)
        await db.commit()
        await db.refresh(peer)
        await record_audit(
            db, event="vpn.peer_create", user_id=user.id, target_id=peer.allocated_ip
        )

    return peer, generated_priv_key


async def generate_vpn_config(
    db: AsyncSession,
    user: CurrentUser,
    client_public_key: str | None = None,
) -> VPNConfigOut:
    """Render an explicitly configured *development* template for a new keypair."""
    _require_vpn_preview()
    endpoint, server_key = _validated_server_settings()
    # A public key supplied by the client cannot be converted to a private key.
    # Returning an importable-looking file with a placeholder would be misleading.
    if client_public_key is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A client private key cannot be recovered from a supplied public key.",
        )
    peer, priv_key = await get_or_create_vpn_peer(db, user)
    if priv_key is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The existing peer's private key cannot be recovered; revoke and register anew.",
        )

    allowed_ips = "10.100.0.0/16, 10.200.0.0/24"

    config_text = f"""[Interface]
# Development preview: the VPN server peer is not provisioned by CyberLab.
PrivateKey = {priv_key}
Address = {peer.allocated_ip}/32

[Peer]
PublicKey = {server_key}
Endpoint = {endpoint}
AllowedIPs = {allowed_ips}
PersistentKeepalive = 25
"""

    return VPNConfigOut(
        config_text=config_text,
        allocated_ip=peer.allocated_ip,
        server_endpoint=endpoint,
        server_public_key=server_key,
        allowed_ips=allowed_ips,
        dns=None,
    )


async def revoke_vpn_peer(db: AsyncSession, user: CurrentUser) -> None:
    """Deactivate a development record; server-side revocation is unsupported."""
    _require_vpn_preview()
    peers = (
        await db.scalars(
            select(VPNPeer).where(VPNPeer.user_id == user.id, VPNPeer.is_active.is_(True))
        )
    ).all()
    for p in peers:
        p.is_active = False
    await db.commit()
    await record_audit(db, event="vpn.peer_revoke", user_id=user.id, target_id=str(user.id))
