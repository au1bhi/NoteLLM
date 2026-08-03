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
# recipient email -> last send timestamp. Guards against one address being
# flooded with verification mail from many different IPs.
_recipient_sends: dict[str, float] = {}
_MAX_ENTRIES = 10_000


def reset() -> None:
    """Clear all buckets (used by tests)."""
    with _lock:
        _buckets.clear()
        _recipient_sends.clear()


def _evict_oldest() -> None:
    """Drop the oldest-bucketed entries when the table grows too large, instead
    of wiping every bucket (which would momentarily open all limits)."""
    with _lock:
        while len(_buckets) > _MAX_ENTRIES:
            oldest_key = min(
                _buckets, key=lambda k: _buckets[k][1]
            )
            del _buckets[oldest_key]


def rate_limit(limit: int, window: int = 60) -> Callable[[Request], None]:
    """Build a FastAPI dependency allowing `limit` requests per `window`
    seconds, keyed by route path and client IP."""

    def dependency(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        host = request.client.host if request.client else "unknown"
        # Key on the ROUTE template path (e.g. `/password-recovery/{email}`),
        # not the concrete path: otherwise each distinct path parameter gets
        # its own bucket and probing many values (e.g. different emails)
        # bypasses the intended per-endpoint throttle.
        route = request.scope.get("route")
        path = getattr(route, "path", None) or request.url.path
        key = (path, host)
        now = time.monotonic()
        with _lock:
            count, start = _buckets.get(key, (0, now))
            if now - start >= window:
                count, start = 0, now
            if count >= limit:
                raise HTTPException(
                    status_code=429,
                    detail=f"请求过于频繁，请稍后再试（{window} 秒内最多 {limit} 次）",
                    headers={"Retry-After": str(window)},
                )
            _buckets[key] = (count + 1, start)
        _evict_oldest()

    return dependency


def recipient_send_cooldown(email: str, window: int = 60) -> bool:
    """Return True if a message may be sent to `email` now.

    Enforces at most one send per `window` seconds per recipient, independent of
    which IP triggers it, so a distributed caller cannot flood a target mailbox
    with verification messages. A rejected call is silently skipped (the caller
    still returns its generic success response).
    """
    if not settings.RATE_LIMIT_ENABLED:
        return True
    now = time.monotonic()
    with _lock:
        last = _recipient_sends.get(email)
        if last is not None and now - last < window:
            return False
        _recipient_sends[email] = now
        # Bound the dict: attackers can enumerate many distinct recipients (or
        # sign up for many addresses) to grow it without bound. Drop the oldest
        # entry past the cap — a cooldown that falls off early only re-opens
        # that one address slightly sooner, never a security boundary.
        if len(_recipient_sends) > _MAX_ENTRIES:
            oldest = min(_recipient_sends, key=lambda k: _recipient_sends[k])
            del _recipient_sends[oldest]
    return True
