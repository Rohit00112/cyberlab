"""Lab provider protocol (Track 4).

Defines the interface that all lab infrastructure backends (Docker, Proxmox, etc.)
must implement. The lab service calls providers through this abstraction rather
than coupling to a specific backend.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LabProviderError(RuntimeError):
    """Raised when a lab provider operation fails."""


class LabProvider(ABC):
    """Abstract base class for lab infrastructure providers."""

    @abstractmethod
    async def ping(self) -> bool:
        """Check if the provider is reachable and healthy."""

    @abstractmethod
    async def ensure_network(self, name: str) -> None:
        """Ensure the named network/vlan exists, creating it if necessary."""

    @abstractmethod
    async def create_lab(
        self,
        name: str,
        image: str,
        network: str,
        *,
        cmd: list[str] | None = None,
        cpu_limit: float | None = None,
        memory_limit_mb: int | None = None,
        pids_limit: int | None = None,
    ) -> tuple[str, str]:
        """Create and start a lab environment.

        Returns (provider_ref, ip_address).
        ``provider_ref`` is the provider-specific identifier (container ID, VMID, etc.).
        """

    @abstractmethod
    async def stop_lab(self, provider_ref: str) -> None:
        """Stop a running lab environment."""

    @abstractmethod
    async def remove_lab(self, provider_ref: str) -> None:
        """Destroy a lab environment and release resources."""

    @abstractmethod
    async def inspect_ip(self, provider_ref: str, network: str) -> str | None:
        """Return the IP address of a lab on a specific network."""

    @abstractmethod
    async def lab_status(self, provider_ref: str) -> dict[str, Any]:
        """Return provider-specific status information about a lab."""

    @abstractmethod
    async def lab_logs(self, provider_ref: str, *, tail: int = 100) -> str:
        """Return recent log output from a lab environment."""
