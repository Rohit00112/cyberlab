"""WireGuard VPN endpoints (Phase 5)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.db.session import get_db
from app.schemas.vpn import VPNConfigOut, VPNPeerOut, VPNPeerRegisterIn
from app.services import vpn as vpn_service

router = APIRouter(tags=["vpn"])


@router.get("/vpn/peer", response_model=VPNPeerOut | None)
async def get_my_vpn_peer(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
):
    """Get active VPN peer registration details for the authenticated user."""
    peer, _ = await vpn_service.get_or_create_vpn_peer(db, user)
    return vpn_service._peer_to_out(peer) if peer else None


@router.post("/vpn/peer", response_model=VPNPeerOut)
async def register_vpn_peer(
    payload: VPNPeerRegisterIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
):
    """Register or renew a WireGuard VPN peer for the authenticated user."""
    peer, _ = await vpn_service.get_or_create_vpn_peer(
        db, user, client_public_key=payload.client_public_key
    )
    return vpn_service._peer_to_out(peer)


@router.delete("/vpn/peer", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_vpn_peer(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
):
    """Revoke and deactivate the authenticated user's VPN peer."""
    await vpn_service.revoke_vpn_peer(db, user)


@router.get("/vpn/config", response_model=VPNConfigOut)
async def get_vpn_config(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
    public_key: str | None = None,
):
    """Generate WireGuard client configuration details."""
    return await vpn_service.generate_vpn_config(db, user, client_public_key=public_key)


@router.get("/vpn/download")
async def download_vpn_config(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.view"))],
    public_key: str | None = None,
):
    """Download ready-to-import cyberlab-vpn.conf WireGuard configuration file."""
    config = await vpn_service.generate_vpn_config(db, user, client_public_key=public_key)
    return Response(
        content=config.config_text,
        media_type="application/x-wireguard-profile",
        headers={"Content-Disposition": 'attachment; filename="cyberlab-vpn.conf"'},
    )
