"""Lab provider factory (Track 4).

Resolves the configured ``lab_provider`` setting to a concrete LabProvider
implementation. Defaults to Docker.
"""
from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.infrastructure.base import LabProvider


@lru_cache
def get_lab_provider() -> LabProvider:
    """Return the configured lab provider singleton."""
    settings = get_settings()
    provider_name = settings.lab_provider

    if provider_name == "proxmox":
        from app.infrastructure.proxmox import ProxmoxLabProvider

        return ProxmoxLabProvider()
    elif provider_name == "fake":
        from app.infrastructure.fake import FakeLabProvider

        return FakeLabProvider()
    else:
        from app.infrastructure.docker import DockerLabProvider

        return DockerLabProvider()
