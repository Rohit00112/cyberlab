"""Lightweight Prometheus-compatible metrics (PRD §47).

Deliberately dependency-free: request counters/histograms are aggregated in
process memory and rendered as Prometheus text on ``GET /metrics``. Lab
instance gauges are computed at scrape time from the database.

Caution: request labels use the raw URL path, so deep user-specific paths add
cardinality. Front the API with a reverse proxy that normalizes paths, or
bucket paths here, before running at scale.
"""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.db.base import SessionLocal

metrics_router = APIRouter(tags=["metrics"])

_counter: defaultdict[tuple[str, str, int], int] = defaultdict(int)
_buckets = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_histogram: defaultdict[tuple[str, str, int, float], int] = defaultdict(int)
_duration_sum: defaultdict[tuple[str, str], float] = defaultdict(float)
_duration_count: defaultdict[tuple[str, str], float] = defaultdict(float)


def record_request(method: str, path: str, status: int, duration_seconds: float) -> None:
    _counter[(method, path, status)] += 1
    for bucket in _buckets:
        if duration_seconds <= bucket:
            _histogram[(method, path, status, bucket)] += 1
    _duration_count[(method, path)] += 1
    _duration_sum[(method, path)] += duration_seconds


def _le_count(method: str, path: str, status: int, le: float) -> int:
    return sum(
        count
        for (m, p, s, b), count in _histogram.items()
        if m == method and p == path and s == status and b <= le
    )


def _escape(label: str) -> str:
    return label.replace("\\", "\\\\").replace('"', '\\"')


def _labels(method: str, path: str, status: int) -> str:
    return (
        f'method="{_escape(method)}",path="{_escape(path)}",'
        f'status="{status}"'
    )


def _render() -> str:
    lines: list[str] = [
        "# HELP cyberlab_http_requests_total HTTP requests by method/path/status.",
        "# TYPE cyberlab_http_requests_total counter",
    ]
    for (method, path, status), count in sorted(_counter.items()):
        lines.append(
            f"cyberlab_http_requests_total{{{_labels(method, path, status)}}} {count}"
        )

    lines.append("# TYPE cyberlab_http_request_duration_seconds histogram")
    for (method, path, status) in sorted(_counter):
        for bucket in _buckets:
            lines.append(
                "cyberlab_http_request_duration_seconds_bucket{"
                f"{_labels(method, path, status)},le=\"{bucket}\"}} "
                f"{_le_count(method, path, status, bucket)}"
            )
        lines.append(
            "cyberlab_http_request_duration_seconds_bucket{"
            f"{_labels(method, path, status)},le=\"+Inf\"}} "
            f"{_counter[(method, path, status)]}"
        )
        lines.append(
            "cyberlab_http_request_duration_seconds_sum{"
            f"{_labels(method, path, status)}}} {_duration_sum[(method, path)]}"
        )
        lines.append(
            "cyberlab_http_request_duration_seconds_count{"
            f"{_labels(method, path, status)}}} {_duration_count[(method, path)]}"
        )

    lines += [
        "# TYPE cyberlab_http_requests_active gauge",
        f"cyberlab_http_requests_active {_active['value']}",
        "# TYPE cyberlab_lab_instances gauge",
        *[
            f'cyberlab_lab_instances{{status="{_escape(status)}"}} {count}'
            for status, count in _lab_counts.items()
        ],
        "# TYPE cyberlab_lab_provisioning_failures gauge",
        f"cyberlab_lab_provisioning_failures {_lab_counts.get('error', 0)}",
    ]
    return "\n".join(lines) + "\n"


_active: dict[str, int] = {"value": 0}
_lab_counts: dict[str, int] = {
    "running": 0,
    "provisioning": 0,
    "stopped": 0,
    "error": 0,
    "expired": 0,
}


def active_requests_inc() -> None:
    _active["value"] += 1


def active_requests_dec() -> None:
    _active["value"] = max(0, _active["value"] - 1)


async def _refresh_lab_counts() -> None:
    try:
        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    text("SELECT status, count(*) FROM lab_instances GROUP BY status")
                )
            ).all()
    except Exception:
        # DB may be briefly unreachable during deploys; serve request metrics
        # with the previous gauge snapshot instead of failing the scrape.
        return
    counts = {key: 0 for key in _lab_counts}
    for status, count in rows:
        if status in counts:
            counts[status] = count
    _lab_counts.update(counts)


@metrics_router.get("/metrics")
async def metrics() -> Response:
    await _refresh_lab_counts()
    return Response(
        content=_render(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )