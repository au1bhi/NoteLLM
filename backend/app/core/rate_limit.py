"""In-process fixed-window rate limiting for auth endpoints.

Sufficient for a single-instance deployment; the bucket state lives only in
this process. For multi-worker deployments, replace the store with a shared
one (e.g. Redis) — the dependency interface stays the same.
"""

import threading
import time
from collections.abc import Callable

from fastapi import HTTPException, Request

from app.core.config import settings

_lock = threading.Lock()
# key -> (count, window_start_seconds). Guarded by _lock.
_buckets: dict[tuple[str, str], tuple[int, float]] = {}
_MAX_ENTRIES = 10_000


def reset() -> None:
    """Clear all buckets (used by tests)."""
    with _lock:
        _buckets.clear()


def rate_limit(limit: int, window: int = 60) -> Callable[[Request], None]:
    """Build a FastAPI dependency allowing `limit` requests per `window`
    seconds, keyed by route path and client IP."""

    def dependency(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        host = request.client.host if request.client else "unknown"
        key = (request.url.path, host)
        now = time.monotonic()
        with _lock:
            count, start = _buckets.get(key, (0, now))
            if now - start >= window:
                count, start = 0, now
            if count >= limit:
                raise HTTPException(
                    status_code=429,
                    detail=f"请求过于频繁，请稍后再试（{window} 秒内最多 {limit} 次）",
                )
            _buckets[key] = (count + 1, start)
            if len(_buckets) > _MAX_ENTRIES:
                _buckets.clear()

    return dependency
