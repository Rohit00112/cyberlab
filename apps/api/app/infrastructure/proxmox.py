"""Proxmox VE lab provider (Track 4).

Implements the LabProvider interface using the Proxmox VE REST API for VM-based
labs. VMs are provisioned from templates with cloud-init for configuration.

Requires Proxmox VE credentials in settings:
  - proxmox_api_url
  - proxmox_api_token_id
  - proxmox_api_token_secret
  - proxmox_node
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.infrastructure.base import LabProvider, LabProviderError

logger = logging.getLogger("cyberlab.proxmox")


class ProxmoxError(LabProviderError):
    """Raised when a Proxmox VE API operation fails."""


class ProxmoxLabProvider(LabProvider):
    """LabProvider implementation backed by Proxmox VE."""

    def __init__(self) -> None:
        settings = get_settings()
        self.api_url = settings.proxmox_api_url.rstrip("/")
        self.node = settings.proxmox_node
        self.headers = {
            "Authorization": (
                f"PVEAPIToken={settings.proxmox_api_token_id}"
                f"={settings.proxmox_api_token_secret}"
            ),
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        url = f"{self.api_url}{path}"
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.request(
                method, url,
                headers=self.headers,
                json=json_data,
                params=params,
            )
            if response.status_code >= 400:
                raise ProxmoxError(
                    f"Proxmox API {method} {path} failed: "
                    f"{response.status_code} {response.text}"
                )
            return response.json().get("data", {})

    async def ping(self) -> bool:
        try:
            await self._request("GET", f"/api2/json/nodes/{self.node}/status")
            return True
        except (ProxmoxError, httpx.HTTPError):
            return False

    async def ensure_network(self, name: str) -> None:
        """Proxmox networks are managed at the node level; this is a no-op
        if the bridge already exists. In practice, SDN or manual VLAN
        configuration is preferred."""
        try:
            await self._request(
                "GET", f"/api2/json/nodes/{self.node}/network/{name}"
            )
        except ProxmoxError:
            logger.warning(
                "Network '%s' not found on node '%s'. "
                "Proxmox networks must be pre-configured.",
                name, self.node,
            )

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
        """Clone a VM template and start it.

        ``image`` is interpreted as the Proxmox template VMID to clone from.
        Returns (new_vmid_str, ip_address).
        """
        # Get next available VMID
        next_id_data = await self._request(
            "GET", "/api2/json/cluster/nextid"
        )
        new_vmid = str(next_id_data) if isinstance(next_id_data, int) else str(next_id_data)

        # Clone from template
        clone_params: dict[str, Any] = {
            "newid": int(new_vmid),
            "name": name,
            "full": 1,
        }
        await self._request(
            "POST",
            f"/api2/json/nodes/{self.node}/qemu/{image}/clone",
            json_data=clone_params,
        )

        # Configure resources
        config_params: dict[str, Any] = {}
        if cpu_limit:
            config_params["cores"] = max(1, int(cpu_limit))
        if memory_limit_mb:
            config_params["memory"] = memory_limit_mb
        if network:
            config_params["net0"] = f"virtio,bridge={network}"

        if config_params:
            await self._request(
                "PUT",
                f"/api2/json/nodes/{self.node}/qemu/{new_vmid}/config",
                json_data=config_params,
            )

        # Start VM
        await self._request(
            "POST",
            f"/api2/json/nodes/{self.node}/qemu/{new_vmid}/status/start",
        )

        # Wait for IP (best effort via QEMU guest agent)
        ip = await self._wait_for_ip(new_vmid)
        return new_vmid, ip or "pending"

    async def _wait_for_ip(self, vmid: str, retries: int = 10) -> str | None:
        """Poll the QEMU guest agent for the VM's IP address."""
        import asyncio

        for _ in range(retries):
            try:
                data = await self._request(
                    "GET",
                    f"/api2/json/nodes/{self.node}/qemu/{vmid}/agent/network-get-interfaces",
                )
                if isinstance(data, dict):
                    result = data.get("result", [])
                elif isinstance(data, list):
                    result = data
                else:
                    result = []
                for iface in result:
                    for addr in iface.get("ip-addresses", []):
                        ip = addr.get("ip-address", "")
                        if (
                            ip
                            and not ip.startswith("127.")
                            and addr.get("ip-address-type") == "ipv4"
                        ):
                            return ip
            except ProxmoxError:
                pass
            await asyncio.sleep(3)
        return None

    async def stop_lab(self, provider_ref: str) -> None:
        await self._request(
            "POST",
            f"/api2/json/nodes/{self.node}/qemu/{provider_ref}/status/stop",
        )

    async def remove_lab(self, provider_ref: str) -> None:
        # Stop first if running
        try:
            await self.stop_lab(provider_ref)
        except ProxmoxError:
            pass
        await self._request(
            "DELETE",
            f"/api2/json/nodes/{self.node}/qemu/{provider_ref}",
        )

    async def inspect_ip(self, provider_ref: str, network: str) -> str | None:
        return await self._wait_for_ip(provider_ref, retries=3)

    async def lab_status(self, provider_ref: str) -> dict[str, Any]:
        try:
            data = await self._request(
                "GET",
                f"/api2/json/nodes/{self.node}/qemu/{provider_ref}/status/current",
            )
            return {
                "status": data.get("status", "unknown"),
                "running": data.get("status") == "running",
                "cpu": data.get("cpu"),
                "mem": data.get("mem"),
                "maxmem": data.get("maxmem"),
                "uptime": data.get("uptime"),
                "pid": data.get("pid"),
            }
        except ProxmoxError as exc:
            return {"error": str(exc)}

    async def lab_logs(self, provider_ref: str, *, tail: int = 100) -> str:
        """Proxmox VMs don't have a unified log stream like Docker.
        Return the most recent syslog lines from the guest agent if available."""
        try:
            data = await self._request(
                "POST",
                f"/api2/json/nodes/{self.node}/qemu/{provider_ref}/agent/exec",
                json_data={"command": f"tail -n {tail} /var/log/syslog"},
            )
            pid = data.get("pid")
            if pid:
                import asyncio

                await asyncio.sleep(2)
                result = await self._request(
                    "GET",
                    f"/api2/json/nodes/{self.node}/qemu/{provider_ref}/agent/exec-status",
                    params={"pid": pid},
                )
                return result.get("out-data", "[no output]")
            return "[no output]"
        except ProxmoxError:
            return "[logs unavailable: guest agent not responding]"
