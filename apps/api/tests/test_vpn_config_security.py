"""VPN preview must fail closed rather than produce misleading production credentials."""
import base64
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import vpn


def _key() -> str:
    return base64.b64encode(bytes(range(32))).decode("ascii")


def test_production_vpn_preview_is_unavailable(monkeypatch):
    monkeypatch.setattr(vpn, "get_settings", lambda: SimpleNamespace(is_production=True))
    with pytest.raises(HTTPException) as exc:
        vpn._require_vpn_preview()
    assert exc.value.status_code == 503


@pytest.mark.parametrize("value", ["", "invalid", "a" * 44, _key() + "\n"])
def test_invalid_server_public_keys_are_rejected(value):
    with pytest.raises(HTTPException) as exc:
        vpn._validated_public_key(value, client=False)
    assert exc.value.status_code == 503


@pytest.mark.parametrize("value", ["", "example.org", "example.org:0", "user@example.org:51820",
                                    "example.org:51820/path", "example.org:51820\n[Peer]"])
def test_invalid_vpn_endpoints_are_rejected(value):
    with pytest.raises(HTTPException) as exc:
        vpn._validated_endpoint(value)
    assert exc.value.status_code == 503


def test_valid_vpn_public_key_and_endpoint():
    assert vpn._validated_public_key(_key(), client=False) == _key()
    assert vpn._validated_endpoint("vpn.example.org:51820") == "vpn.example.org:51820"
