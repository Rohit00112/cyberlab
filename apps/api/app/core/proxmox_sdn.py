"""Parse the operator-managed Proxmox SDN staging VNet pool.

The pool contains only pre-created, applied VNets; CyberLab must never apply
cluster-wide SDN configuration from a student-triggered lab request.
"""
from __future__ import annotations

import ipaddress
import re


def parse_vnet_pool(raw: str) -> tuple[str, ...]:
    if not raw.strip():
        return ()
    names = tuple(part.strip() for part in raw.split(","))
    if not 2 <= len(names) <= 100:
        raise ValueError("Proxmox SDN VNet pool must contain 2..100 VNets")
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,7}", name) for name in names):
        raise ValueError("Invalid Proxmox SDN VNet pool identifier")
    if len(set(names)) != len(names):
        raise ValueError("Proxmox SDN VNet pool contains duplicate identifiers")
    return names


def validate_pool_subnet(rows: object) -> ipaddress.IPv4Network:
    """Require one routed IPv4 subnet with DHCP, and no public SNAT."""
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("SDN pool VNet must have exactly one IPv4 subnet")
    row = rows[0]
    try:
        network = ipaddress.ip_network(row["cidr"], strict=True)
        gateway = ipaddress.ip_address(row["gateway"])
        if not isinstance(network, ipaddress.IPv4Network):
            raise ValueError("IPv6 pool subnets are unsupported")
        if not any(network.subnet_of(ipaddress.ip_network(prefix)) for prefix in (
            "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
        )):
            raise ValueError("SDN pool subnet must be RFC1918 private IPv4")
        if gateway not in network or gateway in (
            network.network_address, network.broadcast_address
        ):
            raise ValueError("SDN pool gateway must be a usable subnet IP")
        if row.get("snat") not in (None, False, 0, "0"):
            raise ValueError("SDN pool SNAT must remain disabled")
        ranges = row.get("dhcp-range")
        if not isinstance(ranges, list) or not ranges:
            raise ValueError("SDN pool subnet requires an IPAM DHCP range")
        for item in ranges:
            start = ipaddress.ip_address(item["start-address"])
            end = ipaddress.ip_address(item["end-address"])
            if start not in network or end not in network or start > end:
                raise ValueError("SDN pool DHCP range falls outside its subnet")
            if gateway >= start and gateway <= end:
                raise ValueError("SDN pool DHCP range includes its gateway")
    except (KeyError, TypeError, ipaddress.AddressValueError, ipaddress.NetmaskValueError) as exc:
        raise ValueError("SDN pool subnet/gateway/DHCP configuration is invalid") from exc
    return network
