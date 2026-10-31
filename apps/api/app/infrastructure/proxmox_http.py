"""HTTPX client for Proxmox API, with an optional IPv6-only transport."""

from __future__ import annotations

import httpx


def make_proxmox_async_client(
    *, verify_ssl: bool, timeout: float, force_ipv6: bool
) -> httpx.AsyncClient:
    """Bind outbound TCP to IPv6 when the configured route's IPv4 path fails.

    This requires outbound IPv6 on the container network. The transport must
    receive ``verify`` itself: configuring it only on AsyncClient would leave
    certificate verification to the transport's defaults.
    """
    if force_ipv6:
        return httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(
                local_address="::", verify=verify_ssl
            ),
            timeout=timeout,
        )
    return httpx.AsyncClient(verify=verify_ssl, timeout=timeout)
