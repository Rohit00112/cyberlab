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


class TestLibvirtFailClosed:
    @pytest.mark.asyncio
    async def test_missing_libvirt_never_claims_a_simulated_environment(self):
        from app.infrastructure.libvirt_provider import LibvirtLabProvider

        provider = LibvirtLabProvider()
        provider._available = False
        with pytest.raises(LabProviderError, match="libvirt-python is not installed"):
            await provider.ensure_network("cyberlab")
        with pytest.raises(LabProviderError, match="libvirt-python is not installed"):
            await provider.create_lab("student-lab", "/tmp/disk.qcow2", "cyberlab")
        with pytest.raises(LabProviderError, match="libvirt-python is not installed"):
            await provider.stop_lab("unverified-domain")
        with pytest.raises(LabProviderError, match="libvirt-python is not installed"):
            await provider.remove_lab("unverified-domain")
        with pytest.raises(LabProviderError, match="libvirt-python is not installed"):
            await provider.inspect_ip("unverified-domain", "cyberlab")
        assert "error" in await provider.lab_status("unverified-domain")

    @pytest.mark.asyncio
    async def test_shutdown_failure_is_reported_not_suppressed(self):
        from app.infrastructure.libvirt_provider import LibvirtLabProvider

        class DeniedConnection:
            def lookupByUUIDString(self, _ref):
                raise RuntimeError("permission denied")

        provider = LibvirtLabProvider()
        provider._available = True
        provider._conn = DeniedConnection()
        with pytest.raises(LabProviderError, match="permission denied"):
            await provider.stop_lab("domain-id")

    @pytest.mark.asyncio
    async def test_domain_xml_escapes_image_network_and_name(self, monkeypatch):
        from unittest.mock import AsyncMock
        from xml.etree import ElementTree

        from app.infrastructure.libvirt_provider import LibvirtLabProvider

        captured = []

        class FakeConnection:
            def createXML(self, xml, _flags):
                captured.append(xml)
                return type("Domain", (), {"UUIDString": lambda self: "domain-uuid"})()

        provider = LibvirtLabProvider()
        provider._available = True
        provider._conn = FakeConnection()
        monkeypatch.setattr(provider, "inspect_ip", AsyncMock(return_value="192.0.2.20"))
        name = "student<&lab"
        image = "/images/lab' <disk>.qcow2"
        network = "lab<&network"
        ref, ip = await provider.create_lab(name, image, network)
        assert ref == "domain-uuid" and ip == "192.0.2.20"
        document = ElementTree.fromstring(captured[0])
        assert document.findtext("name") == name
        assert document.find(".//source[@file]").attrib["file"] == image
        assert document.find(".//source[@network]").attrib["network"] == network
        monkeypatch.setattr(provider, "inspect_ip", AsyncMock(return_value=None))
        _, unresolved_ip = await provider.create_lab("another-lab", image, network)
        assert unresolved_ip == "pending"


@pytest.mark.parametrize("failed_stage", ["start", "inspect"])
@pytest.mark.parametrize("cleanup_fails", [False, True])
async def test_docker_partial_creation_is_cleaned_or_reports_handle(
    monkeypatch, failed_stage, cleanup_fails
):
    import json

    from app.infrastructure import docker
    from app.infrastructure.docker import DockerError

    container_id = "f" * 64
    called = []

    async def engine_request(method, path, body=None):
        called.append((method, path))
        if method == "POST" and "/containers/create?" in path:
            return 201, json.dumps({"Id": container_id}).encode()
        if method == "POST" and path.endswith("/start"):
            return (500 if failed_stage == "start" else 204), b""
        if method == "GET" and path.endswith("/json"):
            return 200, json.dumps({"NetworkSettings": {"Networks": {}}}).encode()
        if method == "DELETE":
            return (500 if cleanup_fails else 204), b""
        raise AssertionError(f"unexpected Docker call: {method} {path}")

    monkeypatch.setattr(docker, "_request", engine_request)
    with pytest.raises(DockerError) as raised:
        await docker.create_and_start_container("lab-test", "alpine:3.20", "lab-net")
    assert raised.value.provider_ref == (container_id if cleanup_fails else None)
    assert ("DELETE", f"/v1.24/containers/{container_id}?force=1&v=1") in called


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

    @pytest.mark.asyncio
    async def test_proxmox_requires_configured_bridge_before_launch(self, monkeypatch):
        from unittest.mock import AsyncMock

        from app.infrastructure.proxmox import ProxmoxError, ProxmoxLabProvider

        provider = ProxmoxLabProvider()
        provider.bridge = "vmbr0"
        request = AsyncMock(side_effect=ProxmoxError("network not found"))
        monkeypatch.setattr(provider, "_request", request)
        with pytest.raises(ProxmoxError, match="vmbr0.*unavailable"):
            await provider.ensure_network("lab-user-dynamic-network")
        request.assert_awaited_once_with(
            "GET", f"/api2/json/nodes/{provider.node}/network/vmbr0"
        )

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
