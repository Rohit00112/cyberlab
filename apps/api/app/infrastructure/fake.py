"""Fake/in-memory lab provider for tests (Track 4).

Tracks lab lifecycle state without any real infrastructure.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.infrastructure.base import LabProvider, LabProviderError


class FakeLabProvider(LabProvider):
    """In-memory lab provider for testing."""

    def __init__(self) -> None:
        self._labs: dict[str, dict[str, Any]] = {}
        self._networks: set[str] = set()

    async def ping(self) -> bool:
        return True

    async def ensure_network(self, name: str) -> None:
        self._networks.add(name)

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
        provider_ref = f"fake-{uuid.uuid4().hex[:12]}"
        ip = f"10.99.0.{len(self._labs) + 2}"
        self._labs[provider_ref] = {
            "name": name,
            "image": image,
            "network": network,
            "ip": ip,
            "status": "running",
            "cmd": cmd,
            "cpu_limit": cpu_limit,
            "memory_limit_mb": memory_limit_mb,
            "pids_limit": pids_limit,
            "logs": [f"[fake] Started {name} from {image} on {network}"],
        }
        return provider_ref, ip

    async def stop_lab(self, provider_ref: str) -> None:
        if provider_ref not in self._labs:
            raise LabProviderError(f"Lab {provider_ref} not found")
        self._labs[provider_ref]["status"] = "stopped"

    async def remove_lab(self, provider_ref: str) -> None:
        if provider_ref not in self._labs:
            return  # Idempotent
        del self._labs[provider_ref]

    async def inspect_ip(self, provider_ref: str, network: str) -> str | None:
        lab = self._labs.get(provider_ref)
        if lab is None:
            return None
        return lab.get("ip")

    async def lab_status(self, provider_ref: str) -> dict[str, Any]:
        lab = self._labs.get(provider_ref)
        if lab is None:
            return {"error": "not found"}
        return {
            "status": lab["status"],
            "running": lab["status"] == "running",
            "name": lab["name"],
            "image": lab["image"],
            "network": lab["network"],
        }

    async def lab_logs(self, provider_ref: str, *, tail: int = 100) -> str:
        lab = self._labs.get(provider_ref)
        if lab is None:
            return "[lab not found]"
        return "\n".join(lab.get("logs", [])[-tail:])
