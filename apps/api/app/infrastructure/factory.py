"""Lab provider factory (Track 4).

Resolves a provider name to a concrete LabProvider implementation. Defaults to
the configured ``lab_provider`` setting (Docker).
"""
from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.infrastructure.base import LabProvider


def _resolve_provider(provider_name: str) -> LabProvider:
    if provider_name == "proxmox":
        from app.infrastructure.proxmox import ProxmoxLabProvider

        return ProxmoxLabProvider()
    if provider_name == "fake":
        from app.infrastructure.fake import FakeLabProvider

        return FakeLabProvider()
    from app.infrastructure.docker import DockerLabProvider

    return DockerLabProvider()


@lru_cache
def get_lab_provider(provider_name: str | None = None) -> LabProvider:
    """Return a cached lab provider singleton.

    ``provider_name`` defaults to the configured ``lab_provider`` setting.
    Callers operating on an *existing* lab instance should pass the lab's
    recorded ``provider`` field so lifecycle operations hit the backend that
    owns the resource (a lab provisioned under ``docker`` must not be sent to
    the Proxmox provider).
    """
    name = provider_name or get_settings().lab_provider
    return _resolve_provider(name)
