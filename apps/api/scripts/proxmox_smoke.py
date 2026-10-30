"""Opt-in, self-cleaning live Proxmox VM and guest-flag smoke test.

Run from the repository root with LAB_PROVIDER=proxmox and --run.
This creates exactly one random-named disposable VM and attempts to remove it
only after the VMID and the clone's identity have both been verified.
"""
from __future__ import annotations

import argparse
import asyncio
import secrets
import shlex
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.core.config import get_settings
from app.core.flags import generate_lab_flag, guest_flag_command
from app.infrastructure.proxmox import ProxmoxLabProvider
from scripts.proxmox_check import ProxmoxCheck


async def _verify_flag(provider: ProxmoxLabProvider, vmid: str, path: str, flag: str) -> None:
    """Ask the guest to compare its flag without returning the flag text."""
    command = [
        "/bin/sh", "-c",
        f"test \"$(cat {shlex.quote(path)})\" = {shlex.quote(flag)}",
    ]
    base = f"/api2/json/nodes/{provider.node}/qemu/{vmid}/agent"
    started = await provider._request(
        "POST", f"{base}/exec", params=[("command", part) for part in command],
    )
    if not isinstance(started, dict):
        raise RuntimeError("Guest-agent verification returned an invalid response")
    result = started.get("result", started)
    pid = result.get("pid") if isinstance(result, dict) else None
    if not isinstance(pid, int) or pid <= 0:
        raise RuntimeError("Guest-agent verification returned no process ID")
    async with asyncio.timeout(45):
        while True:
            state = await provider._request(
                "GET", f"{base}/exec-status", params={"pid": pid},
            )
            result = state.get("result", state) if isinstance(state, dict) else None
            if not isinstance(result, dict):
                raise RuntimeError("Guest-agent verification status is invalid")
            if result.get("exited") is True:
                if result.get("exitcode") != 0:
                    raise RuntimeError("The guest flag did not match the generated flag")
                return
            await asyncio.sleep(1)


async def _remove_owned_vm(
    provider: ProxmoxLabProvider, vmid: str, expected_name: str,
) -> bool:
    """Never delete a VM based on an allocated ID alone."""
    inventory = await provider._request("GET", f"/api2/json/nodes/{provider.node}/qemu")
    if not isinstance(inventory, list):
        raise RuntimeError("Cannot confirm VM inventory; manual cleanup required")
    match = next((item for item in inventory if str(item.get("vmid")) == vmid), None)
    if match is None:
        print(f"cleanup: VMID {vmid} is absent", flush=True)
        return True
    if match.get("name") != expected_name:
        raise RuntimeError(f"VMID {vmid} is not our test VM; refusing deletion")
    config = await provider._request(
        "GET", f"/api2/json/nodes/{provider.node}/qemu/{vmid}/config"
    )
    if not isinstance(config, dict) or config.get("name") != expected_name:
        raise RuntimeError(f"Cannot confirm ownership of VMID {vmid}; refusing deletion")
    print(f"cleanup: stopping/removing verified test VMID {vmid}", flush=True)
    await provider.remove_lab(vmid)
    inventory = await provider._request("GET", f"/api2/json/nodes/{provider.node}/qemu")
    if not isinstance(inventory, list) or any(
        str(item.get("vmid")) == vmid for item in inventory
    ):
        raise RuntimeError(f"VMID {vmid} still appears after cleanup")
    print(f"cleanup: verified VMID {vmid} is absent", flush=True)
    return True


async def _run(execute: bool) -> int:
    settings = get_settings()
    if settings.lab_provider != "proxmox":
        print("Set LAB_PROVIDER=proxmox for this isolated test.", flush=True)
        return 2
    if await ProxmoxCheck().run() != 0:
        return 2
    if not execute:
        print("readiness passed; specify --run to create a disposable VM", flush=True)
        return 0

    provider = ProxmoxLabProvider()
    await provider.ensure_network(provider.bridge)
    expected_vmid = provider._vmid(await provider._request("GET", "/api2/json/cluster/nextid"))
    before = await provider._request("GET", f"/api2/json/nodes/{provider.node}/qemu")
    if not isinstance(before, list) or any(
        str(item.get("vmid")) == expected_vmid for item in before
    ):
        raise RuntimeError("The proposed VMID already exists; refusing test")

    nonce = secrets.token_hex(4)
    name = f"cyberlab-smoke-{nonce}"
    path = f"/tmp/cyberlab-smoke-{nonce}.flag"
    flag = generate_lab_flag()
    success = False
    cleanup_ok = False
    print(
        f"provisioning: template={settings.lab_image} "
        f"target={expected_vmid} name={name}",
        flush=True,
    )
    try:
        vmid, ip = await provider.create_lab(
            name, str(settings.lab_image), provider.bridge,
            cmd=guest_flag_command(path, flag),
            cpu_limit=1, memory_limit_mb=1024,
        )
        if vmid != expected_vmid:
            raise RuntimeError("Provider returned a different VMID; manual review required")
        status = await provider.lab_status(vmid)
        if status.get("status") != "running":
            raise RuntimeError(f"Guest VM is not running: {status.get('status')}")
        await _verify_flag(provider, vmid, path, flag)
        print(f"provisioning: guest flag verified, reported IP={ip}", flush=True)
        success = True
    except Exception as exc:
        print(f"provisioning: {type(exc).__name__}: {exc}", flush=True)
        if exc.__cause__ is not None:
            cause = exc.__cause__
            print(f"provisioning cause: {type(cause).__name__}: {cause}", flush=True)
    finally:
        try:
            cleanup_ok = await _remove_owned_vm(provider, expected_vmid, name)
        except Exception as exc:
            print(f"cleanup: FAILED: {type(exc).__name__}: {exc}", flush=True)
            print(f"MANUAL REVIEW REQUIRED for VMID {expected_vmid} ({name})", flush=True)
    return 0 if success and cleanup_ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="clone, test and remove one VM")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args.run)))
