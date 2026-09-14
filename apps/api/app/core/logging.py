"""Structured JSON logging with request correlation IDs (PRD §47).

Every log line carries at least: timestamp, level, logger, message. When a
request is being processed, a ``request_id`` context variable is set by
``app.api.middleware.RequestContextMiddleware`` and included on all lines for
that request, so a single HTTP call can be traced end-to-end.

Set ``LOG_LEVEL`` (default INFO). The uvicorn access logger is disabled because
the middleware emits a per-request access line in the same JSON format.
"""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFilter(logging.Filter):
    """Injects the active request id onto every record."""

    def __init__(self, name: str = "") -> None:
        self.name = name

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.request_id != "-":
            payload["request_id"] = record.request_id
        for key in (
            "method",
            "path",
            "status_code",
            "duration_ms",
            "user_id",
            "target_id",
            "event",
            "error",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    from app.core.config import get_settings

    level = getattr(logging, get_settings().log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(JsonFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # The middleware already logs one access line per request; skip uvicorn's.
    logging.getLogger("uvicorn.access").disabled = True