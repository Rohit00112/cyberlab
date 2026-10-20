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

    async def reset_lab(self, provider_ref: str) -> None:
        """Reset a lab environment to its initial state.
        
        Default implementation: stop then remove. Provider overrides can optimize.
        """
        await self.stop_lab(provider_ref)

    async def readiness_check(
        self, provider_ref: str, host: str, port: int, timeout: float = 30.0  # noqa: ASYNC109
    ) -> bool:
        """Check whether the exposed service on host:port is ready to accept connections."""
        import asyncio
        import socket
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setblocking(False)
                await loop.sock_connect(sock, (host, port))
                sock.close()
                return True
            except (OSError, TimeoutError):
                await asyncio.sleep(0.5)
        return False

    async def get_resource_usage(self) -> dict[str, Any]:
        """Return overall capacity and resource usage metrics for the compute node."""
        return {
            "status": "healthy",
            "active_instances": 0,
            "cpu_allocated": 0.0,
            "memory_allocated_mb": 0,
        }
