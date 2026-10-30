"""Proxmox VE lab provider (Track 4).

Implements the LabProvider interface using the Proxmox VE REST API for VM-based
labs. VMs are provisioned from templates with cloud-init for configuration.

Requires Proxmox VE credentials in settings (env vars):
  - PROXMOX_ENDPOINT   → proxmox_endpoint
  - PROXMOX_USER       → proxmox_user       (e.g. root@pam!cyberlab)
  - PROXMOX_TOKEN_UUID → proxmox_token_uuid  (API token UUID)
  - PROXMOX_NODE       → proxmox_node
  - PROXMOX_STORAGE    → proxmox_storage
  - PROXMOX_BRIDGE     → proxmox_bridge
  - PROXMOX_VERIFY_SSL → proxmox_verify_ssl
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from app.core.config import get_settings
from app.core.flags import validate_guest_flag_command
from app.infrastructure.base import LabProvider, LabProviderError

logger = logging.getLogger("cyberlab.proxmox")


class ProxmoxError(LabProviderError):
    """Raised when a Proxmox VE API operation fails."""


class ProxmoxLabProvider(LabProvider):
    """LabProvider implementation backed by Proxmox VE."""

    def __init__(self) -> None:
        settings = get_settings()
        self.api_url = settings.proxmox_endpoint.rstrip("/")
        self.node = settings.proxmox_node
        self.storage = settings.proxmox_storage
        self.bridge = settings.proxmox_bridge
        endpoint = urlsplit(self.api_url)
        if endpoint.scheme != "https" or not endpoint.hostname:
            raise ProxmoxError("Proxmox API endpoint must use HTTPS")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}", self.node):
            raise ProxmoxError("Invalid Proxmox node name")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,62}", self.bridge):
            raise ProxmoxError("Invalid Proxmox bridge name")
        self.verify_ssl = settings.proxmox_verify_ssl
        if settings.is_production and not self.verify_ssl:
            raise ProxmoxError("Proxmox TLS certificate verification is required in production")
        if settings.is_production and (
            not settings.proxmox_user or not settings.proxmox_token_uuid
        ):
            raise ProxmoxError("Proxmox API token credentials are required in production")
        # PVE API token header: PVEAPIToken=user@realm!tokenname=token-uuid
        self.headers = {
            "Authorization": (
                f"PVEAPIToken={settings.proxmox_user}"
                f"={settings.proxmox_token_uuid}"
            ),
        }

    @staticmethod
    def _vmid(value: str | int) -> str:
        """Validate a VMID before inserting it into a privileged API path."""
        vmid = str(value)
        if not re.fullmatch(r"[1-9][0-9]{2,8}", vmid):
            raise ProxmoxError("Proxmox VMID must be a numeric identifier >= 100")
        return vmid

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: dict | None = None,
        params: dict | list[tuple[str, str]] | None = None,
    ) -> dict:
        url = f"{self.api_url}{path}"
        async with httpx.AsyncClient(verify=self.verify_ssl, timeout=30) as client:
            try:
                response = await client.request(
                    method, url,
                    headers=self.headers,
                    json=json_data,
                    params=params,
                )
            except httpx.HTTPError as exc:
                raise ProxmoxError(
                    f"Proxmox API {method} {path} unreachable: {exc}"
                ) from exc
        if response.status_code >= 400:
            raise ProxmoxError(
                f"Proxmox API {method} {path} failed: "
                f"{response.status_code} {response.text}"
            )
        if response.status_code >= 300:
            raise ProxmoxError(
                f"Proxmox API {method} {path} unexpected redirect "
                f"{response.status_code} to "
                f"{response.headers.get('location', '')!r}; "
                "the resource id is probably invalid"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise ProxmoxError(
                f"Proxmox API {method} {path} returned a non-JSON body "
                f"({response.status_code}): {exc}"
            ) from exc
        return data.get("data", {}) if isinstance(data, dict) else data

    async def ping(self) -> bool:
        try:
            await self._request("GET", f"/api2/json/nodes/{self.node}/status")
            return True
        except (ProxmoxError, httpx.HTTPError):
            return False

    async def _wait_for_task(self, upid: str, *, max_wait_seconds: float = 120.0) -> None:
        """Wait for an acknowledged Proxmox operation, not just its task ID."""
        if (
            not isinstance(upid, str)
            or not re.fullmatch(r"UPID:[A-Za-z0-9:@!._-]{1,500}", upid)
        ):
            raise ProxmoxError("Proxmox did not return a valid task UPID")
        task_path = (
            f"/api2/json/nodes/{self.node}/tasks/{quote(upid, safe='')}/status"
        )
        try:
            async with asyncio.timeout(max_wait_seconds):
                while True:
                    result = await self._request("GET", task_path)
                    if not isinstance(result, dict):
                        raise ProxmoxError("Proxmox task status response is invalid")
                    state = result.get("status")
                    if state == "stopped":
                        if result.get("exitstatus") != "OK":
                            raise ProxmoxError(
                                f"Proxmox task failed: {result.get('exitstatus', 'unknown')}"
                            )
                        return
                    if state != "running":
                        raise ProxmoxError(
                            f"Proxmox task returned unexpected status: {state!r}"
                        )
                    await asyncio.sleep(1)
        except TimeoutError as exc:
            raise ProxmoxError("Proxmox task did not finish before the deadline") from exc

    async def _install_guest_flag(self, vmid: str, cmd: list[str]) -> None:
        """Execute the one-shot writer through the QEMU guest agent and verify exit 0."""
        try:
            validate_guest_flag_command(cmd)
        except ValueError as exc:
            raise ProxmoxError("Invalid guest flag initializer") from exc
        base = f"/api2/json/nodes/{self.node}/qemu/{self._vmid(vmid)}/agent"
        try:
            async with asyncio.timeout(90):
                # PVE declares command as an alist: repeated command query fields,
                # avoiding a second shell or interpretation by the Proxmox host.
                started = await self._request(
                    "POST", f"{base}/exec",
                    params=[("command", part) for part in cmd],
                )
                pid_data = started.get("result", started) if isinstance(started, dict) else None
                pid = pid_data.get("pid") if isinstance(pid_data, dict) else None
                if not isinstance(pid, int) or pid <= 0:
                    raise ProxmoxError("QEMU guest agent did not return an exec PID")
                while True:
                    status_data = await self._request(
                        "GET", f"{base}/exec-status", params={"pid": pid},
                    )
                    result = (
                        status_data.get("result", status_data)
                        if isinstance(status_data, dict) else None
                    )
                    if not isinstance(result, dict):
                        raise ProxmoxError("Invalid guest exec status")
                    if result.get("exited") is True:
                        if result.get("exitcode") != 0:
                            raise ProxmoxError("Guest flag initializer exited unsuccessfully")
                        return
                    await asyncio.sleep(0.5)
        except TimeoutError as exc:
            raise ProxmoxError("Guest flag initialization exceeded 90 seconds") from exc

    async def ensure_network(self, name: str) -> None:
        """Require an existing provider bridge before any VM is created.

        Dynamic per-user network names belong to Docker; Proxmox guests attach
        to the configured node bridge, which must be provisioned separately.
        """
        bridge = self.bridge or name
        try:
            await self._request(
                "GET", f"/api2/json/nodes/{self.node}/network/{quote(bridge, safe='')}"
            )
        except ProxmoxError as exc:
            raise ProxmoxError(
                f"Proxmox bridge {bridge!r} on node {self.node!r} is unavailable; "
                "configure it before provisioning"
            ) from exc

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
        if cmd:
            try:
                validate_guest_flag_command(cmd)
            except ValueError as exc:
                raise ProxmoxError(
                    "Invalid guest flag command; cannot install a per-lab challenge flag"
                ) from exc
        template_vmid = self._vmid(image)
        # Get next available VMID
        next_id_data = await self._request(
            "GET", "/api2/json/cluster/nextid"
        )
        new_vmid = self._vmid(next_id_data)

        # Clone from template; use configured storage for the full clone
        clone_params: dict[str, Any] = {
            "newid": int(new_vmid),
            "name": name,
            "full": 1,
            "storage": self.storage,
        }
        clone_task = await self._request(
            "POST",
            f"/api2/json/nodes/{self.node}/qemu/{template_vmid}/clone",
            json_data=clone_params,
        )
        await self._wait_for_task(clone_task)

        # Configure resources. Proxmox VMs attach to a physical/SDN bridge;
        # the per-user Docker-style network name cannot be used directly.
        # Prefer the configured bridge over the passed-in network name.
        bridge = self.bridge or network
        config_params: dict[str, Any] = {}
        if cpu_limit:
            config_params["cores"] = max(1, int(cpu_limit))
        if memory_limit_mb:
            config_params["memory"] = memory_limit_mb
        if bridge:
            config_params["net0"] = f"virtio,bridge={bridge}"

        try:
            if config_params:
                await self._request(
                    "PUT",
                    f"/api2/json/nodes/{self.node}/qemu/{new_vmid}/config",
                    json_data=config_params,
                )

            # Start VM and wait for the actual provider task to succeed.
            start_task = await self._request(
                "POST",
                f"/api2/json/nodes/{self.node}/qemu/{new_vmid}/status/start",
            )
            await self._wait_for_task(start_task)
            if cmd:
                await self._install_guest_flag(new_vmid, cmd)
        except ProxmoxError as exc:
            # Do not offer a VMID for destructive cleanup unless the provider
            # confirms that it still belongs to this exact lab.
            try:
                config = await self._request(
                    "GET", f"/api2/json/nodes/{self.node}/qemu/{new_vmid}/config"
                )
            except ProxmoxError:
                raise exc from None
            if isinstance(config, dict) and config.get("name") == name:
                raise ProxmoxError(
                    f"Proxmox VM {new_vmid} failed configuration or startup",
                    provider_ref=new_vmid,
                ) from exc
            raise

        # Wait for IP (best effort via QEMU guest agent)
        ip = await self._wait_for_ip(new_vmid)
        return new_vmid, ip or "pending"

    async def _wait_for_ip(self, vmid: str, retries: int = 10) -> str | None:
        """Poll the QEMU guest agent for the VM's IP address."""
        import asyncio

        vmid = self._vmid(vmid)
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
        provider_ref = self._vmid(provider_ref)
        task = await self._request(
            "POST",
            f"/api2/json/nodes/{self.node}/qemu/{provider_ref}/status/stop",
        )
        await self._wait_for_task(task)

    async def remove_lab(self, provider_ref: str) -> None:
        provider_ref = self._vmid(provider_ref)
        # Stop first if running
        try:
            await self.stop_lab(provider_ref)
        except ProxmoxError as exc:
            current = await self.lab_status(provider_ref)
            if current.get("status") != "stopped":
                raise ProxmoxError(
                    f"Cannot remove VM {provider_ref}: stop was not confirmed"
                ) from exc
        task = await self._request(
            "DELETE",
            f"/api2/json/nodes/{self.node}/qemu/{provider_ref}",
        )
        await self._wait_for_task(task)

    async def inspect_ip(self, provider_ref: str, network: str) -> str | None:
        return await self._wait_for_ip(provider_ref, retries=3)

    async def lab_status(self, provider_ref: str) -> dict[str, Any]:
        try:
            provider_ref = self._vmid(provider_ref)
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
            provider_ref = self._vmid(provider_ref)
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

