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
