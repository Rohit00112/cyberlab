"""IPv6 Proxmox HTTP client configuration is opt-in and preserves TLS policy."""

from __future__ import annotations

import pytest

from app.infrastructure import proxmox_http


@pytest.mark.parametrize("verify_ssl", [True, False])
def test_ipv6_transport_binds_ipv6_and_preserves_tls(monkeypatch, verify_ssl):
    seen: dict[str, object] = {}
    client = object()
    transport = object()

    def fake_transport(**kwargs):
        seen["transport"] = kwargs
        return transport

    def fake_client(**kwargs):
        seen["client"] = kwargs
        return client

    monkeypatch.setattr(proxmox_http.httpx, "AsyncHTTPTransport", fake_transport)
    monkeypatch.setattr(proxmox_http.httpx, "AsyncClient", fake_client)

    result = proxmox_http.make_proxmox_async_client(
        verify_ssl=verify_ssl, timeout=12.5, force_ipv6=True
    )
    assert result is client
    assert seen["transport"] == {"local_address": "::", "verify": verify_ssl}
    assert seen["client"] == {"transport": transport, "timeout": 12.5}


def test_default_proxmox_client_has_no_custom_transport(monkeypatch):
    seen: dict[str, object] = {}
    client = object()

    def fake_client(**kwargs):
        seen.update(kwargs)
        return client

    def forbidden_transport(**kwargs):
        raise AssertionError("IPv6 transport should be disabled by default")

    monkeypatch.setattr(proxmox_http.httpx, "AsyncHTTPTransport", forbidden_transport)
    monkeypatch.setattr(proxmox_http.httpx, "AsyncClient", fake_client)
    assert proxmox_http.make_proxmox_async_client(
        verify_ssl=True, timeout=30, force_ipv6=False
    ) is client
    assert seen == {"verify": True, "timeout": 30}
