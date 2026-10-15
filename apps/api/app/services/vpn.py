"""WireGuard VPN peer management and configuration service (Phase 5)."""

from __future__ import annotations

import base64
import os
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives.asymmetric import x25519
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.models.vpn_scoring import VPNPeer
from app.schemas.vpn import VPNConfigOut, VPNPeerOut
from app.services.users import record_audit

# Default WireGuard subnet parameters
VPN_SUBNET_PREFIX = "10.200.0"
VPN_DEFAULT_ENDPOINT = os.getenv("WIREGUARD_ENDPOINT", "vpn.cyberlab.internal:51820")
VPN_SERVER_PUBLIC_KEY = os.getenv(
    "WIREGUARD_SERVER_PUBLIC_KEY", "CyberLabVPNServerMockPublicKey1234567890="
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
    """Retrieve an active VPN peer for the user, or register a new one.

    Returns (VPNPeer, client_private_key_if_generated).
    """
    peer = (
        await db.scalars(
            select(VPNPeer).where(VPNPeer.user_id == user.id, VPNPeer.is_active.is_(True))
        )
    ).first()

    generated_priv_key: str | None = None

    if not peer:
        if client_public_key:
            pub_key = client_public_key.strip()
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
    """Generate a WireGuard .conf file ready for import into the WireGuard client."""
    peer, priv_key = await get_or_create_vpn_peer(db, user, client_public_key=client_public_key)

    private_key_text = priv_key or "<YOUR_CLIENT_PRIVATE_KEY>"
    allowed_ips = "10.100.0.0/16, 10.200.0.0/24"
    dns_server = f"{VPN_SUBNET_PREFIX}.1"

    config_text = f"""[Interface]
# CyberLab Dedicated Student VPN Peer
PrivateKey = {private_key_text}
Address = {peer.allocated_ip}/32
DNS = {dns_server}

[Peer]
PublicKey = {VPN_SERVER_PUBLIC_KEY}
Endpoint = {VPN_DEFAULT_ENDPOINT}
AllowedIPs = {allowed_ips}
PersistentKeepalive = 25
"""

    return VPNConfigOut(
        config_text=config_text,
        allocated_ip=peer.allocated_ip,
        server_endpoint=VPN_DEFAULT_ENDPOINT,
        server_public_key=VPN_SERVER_PUBLIC_KEY,
        allowed_ips=allowed_ips,
        dns=dns_server,
    )


async def revoke_vpn_peer(db: AsyncSession, user: CurrentUser) -> None:
    """Deactivate any active VPN peer associated with the user."""
    peers = (
        await db.scalars(
            select(VPNPeer).where(VPNPeer.user_id == user.id, VPNPeer.is_active.is_(True))
        )
    ).all()
    for p in peers:
        p.is_active = False
    await db.commit()
    await record_audit(db, event="vpn.peer_revoke", user_id=user.id, target_id=str(user.id))
