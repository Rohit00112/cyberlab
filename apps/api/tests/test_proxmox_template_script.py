"""Fail-closed checks for the Proxmox template builder using fake host CLIs.

No test here talks to a real Proxmox node or creates a virtual machine.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "proxmox_template.sh"


@pytest.fixture
def fake_proxmox(tmp_path: Path) -> tuple[dict[str, str], Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "debian-13-genericcloud-amd64.qcow2").write_bytes(b"pristine-cloud-image")

    commands = {
        "id": '#!/bin/sh\necho 0\n',
        "pvesm": '#!/bin/sh\nprintf "Name Type Status\\nlocal-lvm lvmthin active\\n"\n',
        "ip": '#!/bin/sh\nexit 0\n',
        "curl": '#!/bin/sh\necho "unexpected download" >&2\nexit 50\n',
        "sha512sum": '#!/bin/sh\nexit 0\n',
        "sleep": '#!/bin/sh\nexit 0\n',
        "virt-customize": (
            '#!/bin/sh\n'
            'printf "customize\\n" >> "$FAKE_STATE/commands"\n'
            '[ "$MOCK_CUSTOMIZE_FAIL" = 1 ] && exit 1\n'
            'exit 0\n'
        ),
        "qm": """#!/bin/sh
cmd="$1"
printf '%s\\n' "$cmd" >> "$FAKE_STATE/commands"
case "$cmd" in
  status)
    [ -f "$FAKE_STATE/created" ] || exit 1
    if [ -f "$FAKE_STATE/running" ]; then
      echo 'status: running'
    else
      echo 'status: stopped'
    fi
    ;;
  create) touch "$FAKE_STATE/created" ;;
  config) echo 'unused0: local-lvm:vm-9123-disk-0' ;;
  importdisk|resize) ;;
  set) printf '%s\n' "$*" >> "$FAKE_STATE/set_args" ;;
  start) touch "$FAKE_STATE/running" ;;
  shutdown) : > "$FAKE_STATE/stopped"; rm -f "$FAKE_STATE/running" ;;
  template) touch "$FAKE_STATE/template" ;;
  guest)
    case "$2" in
      cmd) [ "$MOCK_AGENT_FAIL" != 1 ] || exit 1 ;;
      exec)
        if [ "$MOCK_CLEAN_FAIL" = 1 ]; then
          echo '{"exitcode": 1}'
        else
          echo '{"exitcode": 0}'
        fi
        ;;
      *) exit 2 ;;
    esac
    ;;
  *) exit 2 ;;
esac
""",
    }
    for name, source in commands.items():
        path = fake_bin / name
        path.write_text(source)
        path.chmod(0o755)

    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "FAKE_STATE": str(state),
        "PVMID": "9123",
        "PM_BRIDGE": "vmbr-staging",
        "PM_CI_PASS": "temporary-test-password",
        "PM_IMAGE_URL": (
            "https://example.invalid/debian-13-genericcloud-amd64.qcow2"
        ),
        "PM_IMAGE_CACHE_DIR": str(cache),
        "PM_AGENT_WAIT_SECONDS": "5",
        "MOCK_AGENT_FAIL": "0",
        "MOCK_CLEAN_FAIL": "0",
        "MOCK_CUSTOMIZE_FAIL": "0",
    }
    return env, state


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True,
        text=True, timeout=15, check=False,
    )


def test_template_builder_requires_credentials_before_vm_creation(fake_proxmox):
    env, state = fake_proxmox
    env.update(PM_CI_PASS="", PM_SSH_KEY="")
    result = _run(env)
    assert result.returncode != 0
    assert "PM_SSH_KEY" in result.stderr
    assert not (state / "created").exists()


def test_template_builder_refuses_existing_vm(fake_proxmox):
    env, state = fake_proxmox
    (state / "created").touch()
    result = _run(env)
    assert result.returncode != 0
    assert "already exists" in result.stderr
    assert not (state / "template").exists()


def test_template_builder_verifies_agent_cleans_and_sizes_disk(fake_proxmox):
    env, state = fake_proxmox
    result = _run(env)
    assert result.returncode == 0, result.stderr
    assert (state / "template").exists()
    commands = (state / "commands").read_text().splitlines()
    assert "customize" in commands
    assert "resize" in commands
    assert any(
        "--ciupgrade 0" in args
        for args in (state / "set_args").read_text().splitlines()
    )
    assert commands.count("guest") == 4  # ping, Cloud-Init wait/clean, host-key clean
    assert commands.index("template") > commands.index("shutdown")
    assert (
        Path(env["PM_IMAGE_CACHE_DIR"]) / "debian-13-genericcloud-amd64.qcow2"
    ).read_bytes() == b"pristine-cloud-image"


def test_template_builder_refuses_conversion_when_agent_missing(fake_proxmox):
    env, state = fake_proxmox
    env["MOCK_AGENT_FAIL"] = "1"
    result = _run(env)
    assert result.returncode != 0
    assert "guest agent failed" in result.stderr
    assert (state / "created").exists()
    assert not (state / "template").exists()


def test_template_builder_refuses_conversion_when_guest_cleanup_fails(fake_proxmox):
    env, state = fake_proxmox
    env["MOCK_CLEAN_FAIL"] = "1"
    result = _run(env)
    assert result.returncode != 0
    assert "guest command did not exit successfully" in result.stderr
    assert not (state / "template").exists()


def test_template_builder_refuses_conversion_when_bake_fails(fake_proxmox):
    env, state = fake_proxmox
    env["MOCK_CUSTOMIZE_FAIL"] = "1"
    result = _run(env)
    assert result.returncode != 0
    assert "virt-customize failed" in result.stderr
    assert not (state / "created").exists()
