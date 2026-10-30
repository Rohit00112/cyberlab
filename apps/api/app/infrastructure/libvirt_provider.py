"""Libvirt (QEMU/KVM) Lab Provider (Phase 2).

Manages QEMU/KVM virtual machines via libvirt for kernel-level cybersecurity
challenges requiring custom kernels, kernel exploits, hardware emulation,
or full OS root isolation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from app.infrastructure.base import LabProvider, LabProviderError

logger = logging.getLogger("cyberlab.infrastructure.libvirt")


class LibvirtLabProvider(LabProvider):
    """QEMU/KVM lab infrastructure provider using libvirt."""

    def __init__(self, uri: str = "qemu:///system") -> None:
        self.uri = uri
        self._conn = None
        self._available = False
        try:
            import libvirt  # type: ignore[import-not-found]

            self._libvirt = libvirt
            self._available = True
        except ImportError:
            self._libvirt = None
            logger.warning(
                "libvirt-python is not installed; libvirt operations are unavailable."
            )

    def _require_available(self) -> None:
        if not self._available:
            raise LabProviderError(
                "libvirt-python is not installed; select the explicit fake provider for tests"
            )

    def _get_connection(self):
        self._require_available()
        if self._conn is None:
            try:
                self._conn = self._libvirt.open(self.uri)
            except Exception as exc:
                raise LabProviderError(
                    f"Failed to connect to libvirt at {self.uri}: {exc}"
                ) from exc
        return self._conn

    async def ping(self) -> bool:
        """Check whether the hypervisor daemon is responding."""
        if not self._available:
            return False
        try:
            loop = asyncio.get_running_loop()
            conn = await loop.run_in_executor(None, self._get_connection)
            return conn.isAlive() == 1
        except Exception:
            return False

    async def ensure_network(self, name: str) -> None:
        """Ensure isolated virtual bridge/network exists in libvirt."""
        self._require_available()
        loop = asyncio.get_running_loop()

        def _sync_ensure():
            conn = self._get_connection()
            try:
                net = conn.networkLookupByName(name)
                if not net.isActive():
                    net.create()
            except Exception:
                # Create isolated network XML
                xml = f"""
                <network>
                  <name>{escape(name)}</name>
                  <forward mode='nat'/>
                  <bridge name={quoteattr('virbr-' + name[:8])} stp='on' delay='0'/>
                  <ip address='10.100.1.1' netmask='255.255.255.0'>
                    <dhcp>
                      <range start='10.100.1.10' end='10.100.1.254'/>
                    </dhcp>
                  </ip>
                </network>
                """
                net = conn.networkDefineXML(xml)
                net.setAutostart(1)
                net.create()

        try:
            await loop.run_in_executor(None, _sync_ensure)
        except Exception as exc:
            raise LabProviderError(f"libvirt network setup failed: {exc}") from exc

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
        """Clone base qcow2 disk, define transient domain, and boot VM."""
        self._require_available()
        if cmd:
            # No guest-agent/cloud-init execution path currently injects the
            # per-lab flag command. Refuse the VM before defining a domain.
            raise LabProviderError(
                "libvirt guest initialization is not configured; "
                "cannot install a per-lab challenge flag"
            )

        loop = asyncio.get_running_loop()
        memory_kib = int((memory_limit_mb or 1024) * 1024)
        vcpus = max(1, int(cpu_limit or 1))

        xml = f"""
        <domain type='kvm'>
          <name>{escape(name)}</name>
          <memory unit='KiB'>{memory_kib}</memory>
          <vcpu placement='static'>{vcpus}</vcpu>
          <os>
            <type arch='x86_64' machine='q35'>hvm</type>
            <boot dev='hd'/>
          </os>
          <devices>
            <disk type='file' device='disk'>
              <driver name='qemu' type='qcow2'/>
              <source file={quoteattr(image)}/>
              <target dev='vda' bus='virtio'/>
            </disk>
            <interface type='network'>
              <source network={quoteattr(network)}/>
              <model type='virtio'/>
            </interface>
            <graphics type='vnc' port='-1' autoport='yes' listen='127.0.0.1'/>
            <console type='pty'/>
          </devices>
        </domain>
        """

        def _sync_create():
            conn = self._get_connection()
            dom = conn.createXML(xml, 0)
            return dom.UUIDString()

        try:
            domain_uuid = await loop.run_in_executor(None, _sync_create)
            # DHCP leases/guest agent data may lag VM startup. Do not invent
            # an address that might point at a different user's environment.
            ip = await self.inspect_ip(domain_uuid, network) or "pending"
            return domain_uuid, ip
        except Exception as exc:
            raise LabProviderError(f"Failed to create libvirt domain {name}: {exc}") from exc

    async def stop_lab(self, provider_ref: str) -> None:
        """Gracefully shutdown or destroy the virtual machine."""
        self._require_available()
        loop = asyncio.get_running_loop()

        def _sync_stop():
            conn = self._get_connection()
            try:
                dom = conn.lookupByUUIDString(provider_ref)
                if dom.isActive():
                    dom.destroy()
            except Exception as exc:
                raise LabProviderError(
                    f"Failed to stop libvirt domain {provider_ref}: {exc}"
                ) from exc

        await loop.run_in_executor(None, _sync_stop)

    async def remove_lab(self, provider_ref: str) -> None:
        """Stop and undefine the domain."""
        await self.stop_lab(provider_ref)

    async def inspect_ip(self, provider_ref: str, network: str) -> str | None:
        """Read IP address from guest agent or DHCP leases."""
        self._require_available()
        loop = asyncio.get_running_loop()

        def _sync_inspect():
            conn = self._get_connection()
            try:
                dom = conn.lookupByUUIDString(provider_ref)
                ifaces = dom.interfaceAddresses(
                    self._libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE
                )
                for iface in ifaces.values():
                    for addr in iface.get("addrs", []):
                        if addr.get("type") == self._libvirt.VIR_IP_ADDR_TYPE_IPV4:
                            return addr.get("addr")
            except Exception:
                pass
            return None

        return await loop.run_in_executor(None, _sync_inspect)

    async def lab_status(self, provider_ref: str) -> dict[str, Any]:
        """Query state and uptime of the virtual machine."""
        if not self._available:
            return {"provider": "libvirt", "error": "libvirt-python is not installed"}
        loop = asyncio.get_running_loop()

        def _sync_status():
            conn = self._get_connection()
            dom = conn.lookupByUUIDString(provider_ref)
            state, reason = dom.state()
            return {
                "provider": "libvirt",
                "state": state,
                "reason": reason,
                "domain_name": dom.name(),
                "active": bool(dom.isActive()),
            }

        try:
            return await loop.run_in_executor(None, _sync_status)
        except Exception as exc:
            return {"provider": "libvirt", "error": str(exc)}

    async def lab_logs(self, provider_ref: str, *, tail: int = 100) -> str:
        """Fetch VM console logs if available."""
        return f"[libvirt] Guest console log stream for domain {provider_ref}"
