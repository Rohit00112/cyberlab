"""Request correlation middleware (PRD §47).

Sets a ``request_id`` context variable for the whole request (from the
``X-Request-ID`` header or a fresh id), reflects it on the response, and emits
one JSON access-log line per request with method, path, status and duration.
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from typing import Any

from starlette.datastructures import Headers

from app.api.metrics import (
    active_requests_dec,
    active_requests_inc,
    record_request,
)
from app.core.logging import request_id_var

logger = logging.getLogger("cyberlab.access")


def _new_request_id() -> str:
    return uuid.uuid4().hex[:16]


@contextmanager
def request_scope(scope: dict[str, Any]):
    """Set the request-id context variable for the duration of a request scope."""
    headers = Headers(scope=scope)
    rid = headers.get("x-request-id") or _new_request_id()
    token = request_id_var.set(rid)
    try:
        yield rid
    finally:
        request_id_var.reset(token)


class RequestContextMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500

        with request_scope(scope) as rid:
            active_requests_inc()

            async def send_with_context(message: dict[str, Any]) -> None:
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                    headers = list(message.get("headers", []))
                    headers.append((b"x-request-id", rid.encode()))
                    message["headers"] = headers
                await send(message)

            try:
                await self.app(scope, receive, send_with_context)
            finally:
                active_requests_dec()
                elapsed = time.perf_counter() - start
                record_request(
                    str(scope.get("method", "")),
                    str(scope.get("path", "")),
                    status_code,
                    round(elapsed, 4),
                )
                logger.info(
                    "http_request",
                    extra={
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "status_code": status_code,
                        "duration_ms": round(elapsed * 1000, 1),
                    },
                )