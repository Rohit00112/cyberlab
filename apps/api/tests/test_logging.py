"""Tests for structured JSON logging + request correlation (PRD §47)."""
from __future__ import annotations

import json
import logging

import httpx

from app.api.middleware import RequestContextMiddleware
from app.core.config import Settings
from app.core.logging import JsonFilter, JsonFormatter, configure_logging, request_id_var


async def _echo_app(scope, receive, send):
    body = b"pong"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


def test_json_formatter_serializes_fields():
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hello", (), None)
    record.request_id = "rid-1"
    record.method = "GET"
    record.path = "/x"
    record.duration_ms = 1.5

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "rid-1"
    assert payload["method"] == "GET"
    assert payload["path"] == "/x"
    assert payload["duration_ms"] == 1.5
    assert "ts" in payload


def test_json_formatter_omits_default_request_id():
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hi", (), None)
    record.request_id = "-"

    payload = json.loads(JsonFormatter().format(record))

    assert "request_id" not in payload


def test_request_id_contextvar():
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "m", (), None)
    assert request_id_var.get() == "-"
    token = request_id_var.set("from-ctx")
    try:
        assert JsonFilter().filter(record)
    finally:
        request_id_var.reset(token)
    assert record.request_id == "from-ctx"


async def test_middleware_access_log_and_correlation_header(capfd):
    configure_logging()
    wrapped = RequestContextMiddleware(_echo_app)
    transport = httpx.ASGITransport(app=wrapped)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ping", headers={"X-Request-Id": "abc123"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "abc123"

    out, _err = capfd.readouterr()
    lines = [json.loads(line) for line in out.splitlines() if line.strip()]
    access = [entry for entry in lines if entry.get("message") == "http_request"]
    assert len(access) >= 1
    assert access[-1]["request_id"] == "abc123"
    assert access[-1]["method"] == "GET"
    assert access[-1]["path"] == "/ping"
    assert access[-1]["status_code"] == 200
    assert access[-1]["duration_ms"] >= 0


def test_production_env_hides_docs_switch():
    dev = Settings(environment="development")
    prod = Settings(environment="production")

    assert not dev.is_production
    assert prod.is_production