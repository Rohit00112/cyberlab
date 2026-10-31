"""Strict parsing of one-shot flag commands for hypervisor file APIs."""
from __future__ import annotations

import pytest

from app.core.flags import guest_flag_command, guest_flag_write_data


@pytest.mark.parametrize("path,flag", [
    ("/flag.txt", "IIC{sample}"),
    ("/tmp/a file's name.flag", "IIC{quote ' ; $(whoami) }"),
    ("/tmp/flag; not a command", "IIC{a;b&c}"),
])
def test_guest_flag_data_matches_generated_contents(path, flag):
    assert guest_flag_write_data(guest_flag_command(path, flag)) == (
        path, flag + "\n",
    )


@pytest.mark.parametrize("command", [
    ["sh", "-c", "true"],
    ["/bin/sh", "-c", "printf '%s\\n' good > /tmp/flag; rm -rf /tmp/other"],
    ["/bin/sh", "-c", "printf '%s\\n' good > /tmp/flag && true"],
    guest_flag_command("relative.flag", "IIC{test}"),
    guest_flag_command("/tmp/../secret", "IIC{test}"),
    guest_flag_command("/tmp/flag\x00suffix", "IIC{test}"),
    guest_flag_command("/tmp/flag", "IIC{a\x00b}"),
    guest_flag_command("/tmp/flag", "IIC{a\nb}"),
    guest_flag_command("/tmp/flag", ""),
])
def test_guest_flag_data_rejects_unsafe_or_unsupported_commands(command):
    with pytest.raises(ValueError):
        guest_flag_write_data(command)
