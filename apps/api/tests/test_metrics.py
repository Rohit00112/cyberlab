"""Tests for the Prometheus-style /metrics endpoint (PRD §47)."""
from __future__ import annotations

import httpx


async def test_metrics_endpoint_serves_prometheus_text():
    from app.api.metrics import metrics_router

    assert any(getattr(route, "path", None) == "/metrics" for route in metrics_router.routes)

    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/metrics")
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    assert "# TYPE cyberlab_http_requests_total counter" in body
    assert "# TYPE cyberlab_lab_instances gauge" in body
    # The first scrape recorded the request seen by the second scrape.
    assert 'cyberlab_http_requests_total{method="GET",path="/metrics",status="200"}' in body