"""Tests for WireGuard keypair generation and configuration rendering."""

import base64

from app.services.vpn import generate_wireguard_keypair


def test_generate_wireguard_keypair_validity():
    priv, pub = generate_wireguard_keypair()
    assert isinstance(priv, str)
    assert isinstance(pub, str)

    priv_decoded = base64.b64decode(priv)
    pub_decoded = base64.b64decode(pub)

    # Standard Curve25519 keys are 32 bytes
    assert len(priv_decoded) == 32
    assert len(pub_decoded) == 32
