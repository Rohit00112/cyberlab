"""Tests for lab provider abstraction (Track 4)."""
from __future__ import annotations

import pytest

from app.infrastructure.base import LabProviderError
from app.infrastructure.fake import FakeLabProvider


class TestFakeLabProvider:
    @pytest.mark.asyncio
    async def test_ping(self):
        provider = FakeLabProvider()
        assert await provider.ping() is True

    @pytest.mark.asyncio
    async def test_ensure_network(self):
        provider = FakeLabProvider()
        await provider.ensure_network("test-net")
        assert "test-net" in provider._networks

    @pytest.mark.asyncio
    async def test_create_and_inspect(self):
        provider = FakeLabProvider()
        await provider.ensure_network("test-net")
        ref, ip = await provider.create_lab("test-lab", "alpine:3.20", "test-net")
        assert ref.startswith("fake-")
        assert ip.startswith("10.99.0.")
        # Inspect IP
        inspected_ip = await provider.inspect_ip(ref, "test-net")
        assert inspected_ip == ip

    @pytest.mark.asyncio
    async def test_stop(self):
        provider = FakeLabProvider()
        ref, _ = await provider.create_lab("test", "alpine", "net")
        status = await provider.lab_status(ref)
        assert status["running"] is True

        await provider.stop_lab(ref)
        status = await provider.lab_status(ref)
        assert status["running"] is False
        assert status["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_stop_nonexistent_raises(self):
        provider = FakeLabProvider()
        with pytest.raises(LabProviderError):
            await provider.stop_lab("nonexistent")

    @pytest.mark.asyncio
    async def test_remove(self):
        provider = FakeLabProvider()
        ref, _ = await provider.create_lab("test", "alpine", "net")
        await provider.remove_lab(ref)
        status = await provider.lab_status(ref)
        assert status == {"error": "not found"}

    @pytest.mark.asyncio
    async def test_remove_idempotent(self):
        provider = FakeLabProvider()
        # Should not raise
        await provider.remove_lab("nonexistent")

    @pytest.mark.asyncio
    async def test_logs(self):
        provider = FakeLabProvider()
        ref, _ = await provider.create_lab("test", "alpine", "net")
        logs = await provider.lab_logs(ref)
        assert "Started test" in logs

    @pytest.mark.asyncio
    async def test_logs_nonexistent(self):
        provider = FakeLabProvider()
        logs = await provider.lab_logs("nonexistent")
        assert "not found" in logs

    @pytest.mark.asyncio
    async def test_lifecycle(self):
        """Full lifecycle: create -> status -> stop -> remove."""
        provider = FakeLabProvider()
        await provider.ensure_network("lab-net")
        ref, ip = await provider.create_lab(
            "full-test", "ubuntu:22.04", "lab-net",
            cpu_limit=1.0, memory_limit_mb=512,
        )
        assert ref
        assert ip

        status = await provider.lab_status(ref)
        assert status["running"] is True
        assert status["image"] == "ubuntu:22.04"

        await provider.stop_lab(ref)
        status = await provider.lab_status(ref)
        assert status["running"] is False

        await provider.remove_lab(ref)
        assert ref not in provider._labs


class TestProviderFactory:
    def test_docker_default(self):
        from unittest.mock import patch

        # Clear the LRU cache
        from app.infrastructure.factory import get_lab_provider
        get_lab_provider.cache_clear()

        with patch("app.infrastructure.factory.get_settings") as mock:
            mock.return_value.lab_provider = "docker"
            provider = get_lab_provider()
            from app.infrastructure.docker import DockerLabProvider
            assert isinstance(provider, DockerLabProvider)
            get_lab_provider.cache_clear()

    def test_fake_provider(self):
        from unittest.mock import patch

        from app.infrastructure.factory import get_lab_provider
        get_lab_provider.cache_clear()

        with patch("app.infrastructure.factory.get_settings") as mock:
            mock.return_value.lab_provider = "fake"
            provider = get_lab_provider()
            assert isinstance(provider, FakeLabProvider)
            get_lab_provider.cache_clear()

    def test_explicit_provider_name(self):
        from unittest.mock import patch

        from app.infrastructure.factory import get_lab_provider
        get_lab_provider.cache_clear()

        with patch("app.infrastructure.factory.get_settings"):
            assert get_lab_provider("docker") is get_lab_provider("docker")
            assert get_lab_provider("fake") is not get_lab_provider("docker")
            assert isinstance(get_lab_provider("fake"), FakeLabProvider)
        get_lab_provider.cache_clear()

    def test_unknown_provider_fails_closed(self):
        from app.infrastructure.base import LabProviderError
        from app.infrastructure.factory import get_lab_provider

        get_lab_provider.cache_clear()
        with pytest.raises(LabProviderError, match="Unsupported lab provider"):
            get_lab_provider("unconfigured-provider")
        get_lab_provider.cache_clear()


def test_lab_lifecycle_uses_labs_recorded_provider(monkeypatch):
    """Lifecycle ops must target the provider recorded on the lab, so a lab
    provisioned under Docker is not sent to Proxmox after a config switch."""
    from unittest.mock import Mock

    from app.models.labs import LabInstance
    from app.services.labs import _lab_provider_for

    resolve = Mock()
    monkeypatch.setattr("app.services.labs.get_lab_provider", resolve)
    lab = LabInstance(provider="docker", provider_ref="cdf8-...container-id")
    _lab_provider_for(lab)
    resolve.assert_called_once_with("docker")


class TestProxmoxRequest:
    """HTTP-layer regression tests for the Proxmox provider (Track 4)."""

    def _fake_client(self, response):
        class FakeClient:
            def __init__(self, response):
                self._response = response

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def request(self, *args, **kwargs):
                return self._response

        return FakeClient(response)

    @pytest.mark.asyncio
    async def test_redirect_raises_proxmox_error_not_json_error(self, monkeypatch):
        """A 308 redirect (e.g. invalid/non-numeric VMID) must not crash with a
        raw JSONDecodeError — the body is empty and not JSON."""
        from app.infrastructure.proxmox import ProxmoxError, ProxmoxLabProvider

        class FakeResponse:
            status_code = 308
            text = ""
            headers = {"location": "http://pve:8006/api2/json/nodes/x/qemu/"}

            def json(self):
                raise ValueError("Expecting value: line 1 column 1 (char 0)")

        monkeypatch.setattr(
            "app.infrastructure.proxmox.httpx.AsyncClient",
            lambda *a, **kw: self._fake_client(FakeResponse()),
        )
        provider = ProxmoxLabProvider()
        with pytest.raises(ProxmoxError, match="redirect"):
            await provider._request("POST", "/qemu/not-a-vmid/status/stop")

    @pytest.mark.asyncio
    async def test_non_json_body_raises_proxmox_error(self, monkeypatch):
        from app.infrastructure.proxmox import ProxmoxError, ProxmoxLabProvider

        class FakeResponse:
            status_code = 200
            text = "<html>not json</html>"
            headers = {}

            def json(self):
                raise ValueError("Expecting value")

        monkeypatch.setattr(
            "app.infrastructure.proxmox.httpx.AsyncClient",
            lambda *a, **kw: self._fake_client(FakeResponse()),
        )
        provider = ProxmoxLabProvider()
        with pytest.raises(ProxmoxError, match="non-JSON"):
            await provider._request("GET", "/version")

    @pytest.mark.asyncio
    async def test_http_error_wrapped_as_proxmox_error(self, monkeypatch):
        import httpx

        from app.infrastructure.proxmox import ProxmoxError, ProxmoxLabProvider

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def request(self, *args, **kwargs):
                raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(
            "app.infrastructure.proxmox.httpx.AsyncClient",
            lambda *a, **kw: FakeClient(),
        )
        provider = ProxmoxLabProvider()
        with pytest.raises(ProxmoxError, match="unreachable"):
            await provider._request("GET", "/version")
