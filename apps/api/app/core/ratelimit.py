"""Fixed-window rate limiting backed by Redis (PRD §51 Security - rate limiting).

The limiter keys on ``<scope>:<user_id>:<window_index>`` and fails open when
Redis is unreachable so that an operational issue never blocks the service.
"""
from __future__ import annotations

import time

from redis.asyncio import Redis

from app.core.config import get_settings

_redis: Redis | None = None


def set_redis(client: Redis | None) -> None:
    """Inject a Redis client (used by tests; ``None`` resets to lazy init)."""
    global _redis
    _redis = client


async def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
        await _redis.ping()
    return _redis


async def check_rate_limit(key: str, *, limit: int, window_seconds: int) -> bool:
    """Return True when the request is allowed, False when over the limit."""
    try:
        redis = await get_redis()
        bucket = int(time.time()) // window_seconds
        cache_key = f"cyberlab:rl:{key}:{bucket}"
        async with redis.pipeline(transaction=True) as pipe:
            await pipe.incr(cache_key)
            await pipe.expire(cache_key, window_seconds * 2)
            results = await pipe.execute()
        count = int(results[0])
        return count <= limit
    except Exception:
        # Fail open: never degrade availability because of Redis.
        return True