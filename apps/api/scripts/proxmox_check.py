"""Proxmox lab backend readiness check (Track 4).

Queries the live PVE API with the configured token and reports whether the
infrastructure needed to launch labs is actually present:

  * endpoint reachable + credentials accepted
  * configured node is online
  * configured storage exists (clone target)
  * configured bridge exists on the node (VM network)
  * configured template VMID (LAB_IMAGE) exists on the node
  * token has effective privileges to clone, configure and run lab VMs

Run from anywhere the API settings are available (repo root .env):

    uv run --project apps/api python -m scripts.proxmox_check

Exits 0 when proxmox is ready, 1 when something is missing/unreachable.
When ``LAB_PROVIDER != "proxmox"`` the check is skipped (exit 0).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import quote

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

import httpx

from app.core.config import get_settings
from app.core.proxmox_sdn import parse_vnet_pool, validate_pool_subnet
from app.infrastructure.proxmox_http import make_proxmox_async_client

STATUS = {"ok", "warn", "fail"}


def _describe_error(exc: httpx.HTTPError | RuntimeError) -> str:
    """Keep network failures actionable even when HTTPX supplies no message."""
    if isinstance(exc, httpx.TimeoutException):
        return (
            f"{type(exc).__name__}: request timed out; verify the Proxmox API "
            "endpoint, network route, tunnel, and firewall"
        )
    detail = str(exc).strip()
    return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__


class ProxmoxCheck:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.api_url = self.settings.proxmox_endpoint.rstrip("/")
        self.node = self.settings.proxmox_node
        self.storage = self.settings.proxmox_storage
        self.sdn_vnet = getattr(self.settings, "proxmox_sdn_vnet", "").strip()
        self.pool_error: str | None = None
        try:
            self.sdn_pool = parse_vnet_pool(
                getattr(self.settings, "proxmox_sdn_vnet_pool", "")
            )
        except ValueError as exc:
            self.sdn_pool = ()
            self.pool_error = str(exc)
        self.sdn_zones: dict[str, str] = {}
        self.bridge = self.sdn_vnet or self.settings.proxmox_bridge
        self.template_vmid = str(self.settings.lab_image)
        self.headers = {
            "Authorization": (
                f"PVEAPIToken={self.settings.proxmox_user}"
                f"={self.settings.proxmox_token_uuid}"
            )
        }
        self.results: list[tuple[str, str, str]] = []  # (status, label, detail)

    def _serve(self, label: str, status: str, detail: str) -> None:
        self.results.append((status, label, detail))

    async def _get(self, path: str, request_timeout: float = 10.0) -> httpx.Response:
        async with make_proxmox_async_client(
            verify_ssl=self.settings.proxmox_verify_ssl,
            timeout=request_timeout,
            force_ipv6=getattr(self.settings, "proxmox_force_ipv6", False),
        ) as client:
            response = await client.get(
                f"{self.api_url}/api2/json{path}", headers=self.headers
            )
        return response

    def _data(self, response: httpx.Response) -> object:
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text}")
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(f"non-JSON body ({response.status_code})") from exc
        return body.get("data") if isinstance(body, dict) else body

    async def _check_permissions(
        self, next_vmid: str | None, bridges: set[str] | None = None
    ) -> None:
        """Check token's effective rights on the source, target and storage.

        Privilege-separated tokens do not inherit the root user's permissions;
        a successful API login and readable VM inventory are insufficient.
        """
        checks = [
            ("perm-clone", f"/vms/{self.template_vmid}", {"VM.Clone"}),
            ("perm-storage", f"/storage/{self.storage}", {"Datastore.AllocateSpace"}),
        ]
        if next_vmid is not None:
            checks.append((
                "perm-target", f"/vms/{next_vmid}",
                {
                    "VM.Allocate", "VM.Config.CPU", "VM.Config.Memory",
                    "VM.Config.Network", "VM.PowerMgmt",
                    "VM.GuestAgent.Unrestricted",
                },
            ))
        for bridge in sorted(bridges or {self.bridge}):
            if bridge in (*self.sdn_pool, self.sdn_vnet) and bridge not in self.sdn_zones:
                self._serve(
                    "perm-bridge", "fail",
                    f"'{bridge}': SDN VNet zone cannot be verified",
                )
                continue
            zone = self.sdn_zones.get(bridge, "localnetwork")
            checks.append((
                "perm-bridge", f"/sdn/zones/{zone}/{bridge}", {"SDN.Use"},
            ))

        for label, path, required in checks:
            try:
                data = self._data(await self._get(
                    f"/access/permissions?path={quote(path, safe='')}"
                ))
                if not isinstance(data, dict) or not isinstance(data.get(path), dict):
                    raise RuntimeError("unexpected effective permissions response")
                granted = {
                    privilege for privilege, enabled in data[path].items()
                    if enabled in (1, "1", True)
                }
                missing = sorted(required - granted)
                self._serve(
                    label, "fail" if missing else "ok",
                    f"{path}: missing {', '.join(missing)}" if missing
                    else f"{path}: required privileges granted",
                )
            except (httpx.HTTPError, RuntimeError) as exc:
                self._serve(label, "fail", f"{path}: {_describe_error(exc)}")

    async def run(self) -> int:
        if self.settings.lab_provider != "proxmox":
            print(
                f"LAB_PROVIDER={self.settings.lab_provider} — skipping Proxmox checks."
            )
            return 0

        if getattr(self.settings, "is_production", False):
            self._serve(
                "isolation", "fail",
                "Production Proxmox VM launch is disabled: the configured "
                "bridge/VNet is shared; per-user SDN and VPN/firewall "
                "enforcement have not been implemented",
            )
            return self._print_and_exit()

        if self.pool_error or (self.sdn_pool and self.sdn_vnet):
            self._serve(
                "sdn-pool", "fail",
                self.pool_error or "SDN VNet pool conflicts with shared staging VNet",
            )
            return self._print_and_exit()

        if self.api_url.startswith("http://"):
            self._serve(
                "endpoint", "warn",
                f"{self.api_url} uses plain http — PVE redirects to https with "
                "empty-body 301/308 responses; use PROXMOX_ENDPOINT=https://…",
            )

        # Endpoint + auth
        try:
            response = await self._get("/version")
            version = self._data(response)
            self._serve(
                "auth", "ok",
                f"reachable via {self.api_url}, PVE "
                f"{version.get('version', '?') if isinstance(version, dict) else version}",
            )
        except httpx.HTTPError as exc:
            self._serve("auth", "fail", f"unreachable: {_describe_error(exc)}")
            return self._print_and_exit()
        except RuntimeError as exc:
            self._serve("auth", "fail", _describe_error(exc))
            return self._print_and_exit()

        # Node
        try:
            nodes = self._data(await self._get("/nodes"))
            if not isinstance(nodes, list):
                raise RuntimeError("unexpected node list format")
            match = next((n for n in nodes if n.get("node") == self.node), None)
            if match is None:
                self._serve(
                    "node", "fail",
                    f"node '{self.node}' not found in cluster "
                    f"({', '.join(str(n.get('node')) for n in nodes) or 'none'})",
                )
            else:
                self._serve(
                    "node", "ok",
                    f"'{self.node}' is {match.get('status')}",
                )
        except (httpx.HTTPError, RuntimeError) as exc:
            self._serve("node", "fail", _describe_error(exc))

        # Storage
        try:
            storages = self._data(await self._get(f"/nodes/{self.node}/storage"))
            storage = next(
                (s for s in storages if s.get("storage") == self.storage), None
            )
            if storage is None:
                self._serve(
                    "storage", "fail",
                    f"'{self.storage}' not configured on node "
                    f"({', '.join(str(s.get('storage')) for s in storages) or 'none'})",
                )
            else:
                content = {c.strip() for c in storage.get("content", "").split(",")}
                # VM full clones require disk-image content; rootdir alone is
                # usable for LXC containers, not CyberLab QEMU VM disks.
                ok_content = "images" in content
                self._serve(
                    "storage", "ok" if ok_content else "fail",
                    f"'{self.storage}' ({storage.get('type')}) content={storage.get('content')}",
                )
        except (httpx.HTTPError, RuntimeError) as exc:
            self._serve("storage", "fail", _describe_error(exc))

        # Bridge
        try:
            if self.sdn_vnet or self.sdn_pool:
                seen_subnets = {}
                for vnet_name in self.sdn_pool or (self.sdn_vnet,):
                    try:
                        vnet = self._data(await self._get(
                            f"/cluster/sdn/vnets/{quote(vnet_name, safe='')}"
                        ))
                        if (
                            not isinstance(vnet, dict)
                            or vnet.get("vnet") != vnet_name
                            or not isinstance(vnet.get("zone"), str)
                            or not re.fullmatch(
                                r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}", vnet["zone"]
                            )
                        ):
                            raise RuntimeError("SDN VNet is missing or malformed")
                        zone = vnet["zone"]
                        statuses = self._data(await self._get(
                            f"/nodes/{self.node}/sdn/zones"
                        ))
                        if not isinstance(statuses, list) or not any(
                            isinstance(item, dict)
                            and item.get("zone") == zone
                            and item.get("status") == "available"
                            for item in statuses
                        ):
                            raise RuntimeError(f"SDN zone '{zone}' not available on node")
                        bridges = self._data(await self._get(
                            f"/nodes/{self.node}/sdn/zones/{quote(zone, safe='')}/bridges"
                        ))
                        if not isinstance(bridges, list) or not any(
                            isinstance(item, dict) and item.get("name") == vnet_name
                            for item in bridges
                        ):
                            raise RuntimeError(f"SDN bridge '{vnet_name}' is not active")
                        if self.sdn_pool:
                            subnet_rows = self._data(await self._get(
                                f"/cluster/sdn/vnets/{quote(vnet_name, safe='')}/subnets"
                            ))
                            try:
                                subnet = validate_pool_subnet(subnet_rows)
                            except ValueError as exc:
                                raise RuntimeError(str(exc)) from exc
                            for other_vnet, other_subnet in seen_subnets.items():
                                if subnet.overlaps(other_subnet):
                                    raise RuntimeError(
                                        f"Subnet {subnet} overlaps VNet '{other_vnet}'"
                                    )
                            seen_subnets[vnet_name] = subnet
                        self.sdn_zones[vnet_name] = zone
                        self._serve(
                            "bridge", "ok",
                            f"'{vnet_name}' (SDN zone={zone}, available)",
                        )
                    except (httpx.HTTPError, RuntimeError) as exc:
                        self._serve(
                            "bridge", "fail", f"{vnet_name}: {_describe_error(exc)}"
                        )
            else:
                ifaces = self._data(await self._get(f"/nodes/{self.node}/network"))
                bridge = next(
                    (i for i in ifaces if i.get("iface") == self.bridge), None
                )
                if bridge is None:
                    self._serve(
                        "bridge", "fail",
                        f"'{self.bridge}' not present on node "
                        f"({', '.join(str(i.get('iface')) for i in ifaces) or 'none'})",
                    )
                else:
                    self._serve(
                        "bridge", "ok",
                        f"'{self.bridge}' (type={bridge.get('type')}, zone=localnetwork)",
                    )
        except (httpx.HTTPError, RuntimeError) as exc:
            self._serve("bridge", "fail", _describe_error(exc))

        # Template
        docker_like = re.search(r"[:/.]", self.template_vmid)
        try:
            vms = self._data(await self._get(f"/nodes/{self.node}/qemu"))
            template = next(
                (v for v in vms if str(v.get("vmid")) == self.template_vmid), None
            )
            if docker_like:
                self._serve(
                    "template", "fail",
                    f"LAB_IMAGE='{self.template_vmid}' looks like a Docker image name; "
                    "it must be a numeric PVE template VMID",
                )
            elif template is None:
                self._serve(
                    "template", "fail",
                    f"template VMID {self.template_vmid} not found on node "
                    f"({', '.join(str(v.get('vmid')) for v in vms) or 'no VMs yet'})",
                )
            elif not template.get("template"):
                self._serve(
                    "template", "fail",
                    f"VMID {self.template_vmid} exists but is not a template",
                )
            else:
                self._serve(
                    "template", "ok",
                    f"'{template.get('name')}' template={template.get('vmid')} "
                    f"status={template.get('status')}",
                )
        except (httpx.HTTPError, RuntimeError) as exc:
            self._serve("template", "fail", _describe_error(exc))

        # A clone requires an available target VMID and effective permissions
        # on that target, separately from the source template.
        next_vmid = None
        try:
            next_id = self._data(await self._get("/cluster/nextid"))
            if not re.fullmatch(r"[1-9][0-9]{2,8}", str(next_id)):
                raise RuntimeError("Proxmox did not return a valid free VMID")
            next_vmid = str(next_id)
            self._serve("nextid", "ok", f"next free VMID is {next_vmid}")
        except (httpx.HTTPError, RuntimeError) as exc:
            self._serve("nextid", "fail", _describe_error(exc))

        # Proxmox checks SDN.Use for both the template's inherited NICs and
        # the replacement bridge configured after cloning. Plain vmbr bridges
        # belong to the implicit localnetwork zone.
        bridges = set(self.sdn_pool or (self.bridge,))
        try:
            if not re.fullmatch(r"[1-9][0-9]{2,8}", self.template_vmid):
                raise RuntimeError("LAB_IMAGE must be a numeric Proxmox template VMID")
            config = self._data(await self._get(
                f"/nodes/{self.node}/qemu/{self.template_vmid}/config"
            ))
            if not isinstance(config, dict):
                raise RuntimeError("invalid source template configuration")
            for key, value in config.items():
                if re.fullmatch(r"net\d+", key) and isinstance(value, str):
                    matched = re.search(r"(?:^|,)bridge=([A-Za-z0-9_.:-]+)(?:,|$)", value)
                    if matched:
                        bridges.add(matched.group(1))
        except (httpx.HTTPError, RuntimeError) as exc:
            self._serve("template-net", "fail", _describe_error(exc))

        await self._check_permissions(next_vmid, bridges)

        return self._print_and_exit()

    def _print_and_exit(self) -> int:
        failed = False
        icons = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}
        for status, label, detail in self.results:
            print(f"[{icons[status]:>4}] {label:<10} {detail}")
            failed = failed or status == "fail"
        print("")
        if failed:
            print("proxmox: not ready — resolve every FAIL row above.")
        else:
            print("proxmox: ready.")
        return 1 if failed else 0


async def _main() -> None:
    raise SystemExit(await ProxmoxCheck().run())


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main())
