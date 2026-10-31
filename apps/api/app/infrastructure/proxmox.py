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
  - PROXMOX_FORCE_IPV6 → proxmox_force_ipv6 (opt-in IPv6-only API transport)
  - PROXMOX_AGENT_WAIT_SECONDS → proxmox_agent_wait_seconds (default 300)
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import re
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from app.core.config import get_settings
from app.core.flags import guest_flag_write_data
from app.core.proxmox_sdn import parse_vnet_pool, validate_pool_subnet
from app.infrastructure.base import LabProvider, LabProviderError
from app.infrastructure.proxmox_http import make_proxmox_async_client

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
        self.sdn_vnet = settings.proxmox_sdn_vnet.strip()
        try:
            self.sdn_pool = parse_vnet_pool(settings.proxmox_sdn_vnet_pool)
        except ValueError as exc:
            raise ProxmoxError(str(exc)) from exc
        if self.sdn_pool and self.sdn_vnet:
            raise ProxmoxError(
                "Proxmox SDN pool and shared staging VNet cannot both be enabled"
            )
        self.bridge = self.sdn_vnet or settings.proxmox_bridge
        endpoint = urlsplit(self.api_url)
        if endpoint.scheme != "https" or not endpoint.hostname:
            raise ProxmoxError("Proxmox API endpoint must use HTTPS")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}", self.node):
            raise ProxmoxError("Invalid Proxmox node name")
        if self.sdn_vnet and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,7}", self.sdn_vnet):
            raise ProxmoxError("Invalid Proxmox SDN VNet name")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,62}", self.bridge):
            raise ProxmoxError("Invalid Proxmox bridge name")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}", self.storage):
            raise ProxmoxError("Invalid Proxmox storage identifier")
        self.verify_ssl = settings.proxmox_verify_ssl
        self.force_ipv6 = settings.proxmox_force_ipv6
        self.agent_wait_seconds = settings.proxmox_agent_wait_seconds
        if not 30 <= self.agent_wait_seconds <= 900:
            raise ProxmoxError("Proxmox agent wait must be 30..900 seconds")
        if settings.is_production and not self.verify_ssl:
            raise ProxmoxError("Proxmox TLS certificate verification is required in production")
        if settings.is_production and (
            not settings.proxmox_user or not settings.proxmox_token_uuid
        ):
            raise ProxmoxError("Proxmox API token credentials are required in production")
        # The current provider connects all guests to one configured bridge or
        # VNet. A per-user network_name from the lab service does not isolate
        # those guests at L2, and no verified per-student VPN/firewall policy
        # exists yet. Refuse production provisioning until that is implemented.
        if settings.is_production:
            raise ProxmoxError(
                "Proxmox shared bridge/VNet is staging-only; per-student "
                "SDN isolation and VPN/firewall enforcement are required for production"
            )
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
        async with make_proxmox_async_client(
            verify_ssl=self.verify_ssl, timeout=30, force_ipv6=self.force_ipv6
        ) as client:
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
        """Write and read back the flag via QGA without a guest-exec PID race."""
        try:
            flag_path, flag_content = guest_flag_write_data(cmd)
        except ValueError as exc:
            raise ProxmoxError("Invalid guest flag initializer") from exc
        base = f"/api2/json/nodes/{self.node}/qemu/{self._vmid(vmid)}/agent"
        last_ping_error: ProxmoxError | None = None
        try:
            async with asyncio.timeout(self.agent_wait_seconds):
                # A successful qmstart task means the hypervisor accepted the
                # start request; the guest OS and qemu-guest-agent may still
                # need time to boot before guest file operations are available.
                while True:
                    try:
                        await self._request("POST", f"{base}/ping")
                        break
                    except ProxmoxError as exc:
                        last_ping_error = exc
                        await asyncio.sleep(2)

                await self._request(
                    "POST", f"{base}/file-write",
                    json_data={"file": flag_path, "content": flag_content},
                )
                checked = await self._request(
                    "GET", f"{base}/file-read", params={"file": flag_path},
                )
                content = checked.get("content") if isinstance(checked, dict) else None
                if not isinstance(content, str) or not hmac.compare_digest(
                    content, flag_content
                ):
                    raise ProxmoxError("Guest flag read-back did not match")
        except TimeoutError as exc:
            detail = f"; last agent error: {last_ping_error}" if last_ping_error else ""
            raise ProxmoxError(
                f"Guest flag initialization exceeded {self.agent_wait_seconds} seconds{detail}"
            ) from exc

    async def ensure_network(self, name: str) -> None:
        """Require a pre-created, applied staging network before VM allocation.

        Pooled guests use their exclusively reserved VNet. Without a pool,
        guests still share the configured bridge/VNet; neither option permits
        production launches until actual VPN/firewall isolation is verified.
        """
        if self.sdn_pool:
            if name not in self.sdn_pool:
                raise ProxmoxError("Requested Proxmox SDN VNet is not in the approved pool")
            await self._require_sdn_vnet(name)
            return
        if self.sdn_vnet:
            await self._require_sdn_vnet()
            return
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

    async def _require_sdn_vnet(self, vnet_name: str | None = None) -> None:
        """Fail closed unless the VNet is live in its SDN zone on this node.

        Generated SDN bridges appear under /nodes/{node}/sdn/zones, not
        necessarily under the ordinary /nodes/{node}/network inventory.
        """
        vnet_name = vnet_name or self.sdn_vnet
        vnet = quote(vnet_name, safe="")
        try:
            definition = await self._request("GET", f"/api2/json/cluster/sdn/vnets/{vnet}")
            zone = definition.get("zone") if isinstance(definition, dict) else None
            if (
                not isinstance(definition, dict)
                or definition.get("vnet") != vnet_name
                or not isinstance(zone, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}", zone)
            ):
                raise ProxmoxError("SDN VNet definition is missing or invalid")
            status = await self._request(
                "GET", f"/api2/json/nodes/{self.node}/sdn/zones"
            )
            if not isinstance(status, list) or not any(
                isinstance(item, dict)
                and item.get("zone") == zone
                and item.get("status") == "available"
                for item in status
            ):
                raise ProxmoxError("SDN zone is not available on this node")
            bridges = await self._request(
                "GET", f"/api2/json/nodes/{self.node}/sdn/zones/{quote(zone, safe='')}/bridges"
            )
            if not isinstance(bridges, list) or not any(
                isinstance(item, dict) and item.get("name") == vnet_name
                for item in bridges
            ):
                raise ProxmoxError("SDN VNet bridge is not active in its zone")
            if self.sdn_pool:
                # The launch path must recheck the *whole* operator-managed
                # pool, not just this student's bridge. A later SDN change
                # could overlap an existing student's subnet after the
                # read-only deployment readiness check was last run.
                seen_subnets = {}
                for member in self.sdn_pool:
                    member_id = quote(member, safe="")
                    subnets = await self._request(
                        "GET", f"/api2/json/cluster/sdn/vnets/{member_id}/subnets"
                    )
                    try:
                        subnet = validate_pool_subnet(subnets)
                    except ValueError as exc:
                        raise ProxmoxError(
                            f"SDN pool member {member!r} has an invalid subnet: {exc}"
                        ) from exc
                    for other_member, other_subnet in seen_subnets.items():
                        if subnet.overlaps(other_subnet):
                            raise ProxmoxError(
                                f"SDN pool subnet overlap: {member!r} ({subnet}) "
                                f"and {other_member!r} ({other_subnet})"
                            )
                    seen_subnets[member] = subnet
        except ProxmoxError as exc:
            raise ProxmoxError(
                f"Proxmox SDN VNet {vnet_name!r} is not configured and applied "
                f"on node {self.node!r}; refuse to provision"
            ) from exc

    async def _verify_clone_prerequisites(self, template_vmid: str) -> None:
        """Reject unsuitable templates/storage before allocating any VM.

        Proxmox allows an ordinary stopped VM and an ISO-only datastore to be
        inspected successfully, but neither is a valid source/target for the
        full-clone workflow used by CyberLab.
        """
        inventory = await self._request(
            "GET", f"/api2/json/nodes/{self.node}/qemu"
        )
        if not isinstance(inventory, list):
            raise ProxmoxError("Cannot verify Proxmox VM template inventory")
        template = next(
            (item for item in inventory
             if isinstance(item, dict) and str(item.get("vmid")) == template_vmid),
            None,
        )
        if template is None or template.get("template") not in (1, "1", True):
            raise ProxmoxError(
                f"Proxmox VMID {template_vmid} is not an available VM template"
            )

        storage = await self._request(
            "GET",
            f"/api2/json/nodes/{self.node}/storage/{quote(self.storage, safe='')}/status",
        )
        if not isinstance(storage, dict) or storage.get("active") not in (1, "1", True):
            raise ProxmoxError(f"Proxmox storage {self.storage!r} is not active")
        contents = storage.get("content", "")
        if not isinstance(contents, str) or "images" not in {
            item.strip() for item in contents.split(",")
        }:
            raise ProxmoxError(
                f"Proxmox storage {self.storage!r} cannot hold VM disk images"
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
        if cmd:
            try:
                guest_flag_write_data(cmd)
            except ValueError as exc:
                raise ProxmoxError(
                    "Invalid guest flag command; cannot install a per-lab challenge flag"
                ) from exc
        if self.sdn_pool:
            if network not in self.sdn_pool:
                raise ProxmoxError("Requested Proxmox SDN VNet is not in the approved pool")
            await self._require_sdn_vnet(network)
        elif self.sdn_vnet:
            await self._require_sdn_vnet()
        template_vmid = self._vmid(image)
        # Get next available VMID
        next_id_data = await self._request(
            "GET", "/api2/json/cluster/nextid"
        )
        new_vmid = self._vmid(next_id_data)
        await self._verify_clone_prerequisites(template_vmid)

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
        bridge = network if self.sdn_pool else (self.bridge or network)
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

