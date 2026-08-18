"""PostgreSQL-backed fixed-window rate limiting shared by all workers."""

import hashlib
import ipaddress
import logging
import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request
from sqlalchemy import text as sql_text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine

_UPDATE_ACTIVE_SQL = sql_text(
    """
    UPDATE rate_limit_bucket SET
      count = CASE
        WHEN rate_limit_bucket.window_started_at <= :cutoff THEN 1
        ELSE rate_limit_bucket.count + 1
      END,
      window_started_at = CASE
        WHEN rate_limit_bucket.window_started_at <= :cutoff THEN :now
        ELSE rate_limit_bucket.window_started_at
      END,
      updated_at = :now
    WHERE key = :key AND updated_at >= :retention_cutoff
    RETURNING count, window_started_at
    """
)

_INSERT_SQL = sql_text(
    """
    INSERT INTO rate_limit_bucket (key, count, window_started_at, updated_at)
    VALUES (:key, 1, :now, :now)
    RETURNING count, window_started_at
    """
)

# Transaction-level lock used only while admitting a new active bucket. Existing
# buckets stay on the lock-free UPDATE path.
_ADMISSION_LOCK_ID = 0x4E6F74654C4C4D
_RETENTION = timedelta(hours=1)
_UNDEFINED_TABLE_SQLSTATE = "42P01"
_UNAVAILABLE_DETAIL = "请求保护服务暂时不可用，请稍后重试"
_UNINITIALIZED_DETAIL = "请求保护服务尚未初始化，请联系管理员"
_TRANSIENT_RETRY_SECONDS = 5
_SCHEMA_RETRY_SECONDS = 30

logger = logging.getLogger(__name__)


def _trusted_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    values = settings.TRUSTED_PROXY_CIDRS
    if isinstance(values, str):
        values = [item.strip() for item in values.split(",") if item.strip()]
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for value in values:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return networks


def _is_trusted(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return any(address in network for network in _trusted_networks())


def _valid_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_ip(request: Request) -> str:
    """Resolve the client through a trusted proxy chain.

    Forwarding headers are ignored unless the raw TCP peer is trusted. The
    application never consumes provider-specific headers; ingress must convert
    a verified client address to XFF. XFF is peeled from right to left,
    discarding only configured proxy hops.
    """
    peer = request.client.host if request.client else "unknown"
    if not _is_trusted(peer):
        return peer

    forwarded = request.headers.get("x-forwarded-for", "")
    hops = [parsed for hop in forwarded.split(",") if (parsed := _valid_ip(hop))]
    for hop in reversed([*hops, peer]):
        if not _is_trusted(hop):
            return hop
    return hops[0] if hops else peer


def _rate_limit_identity(value: str) -> str:
    """Keep IPv4 exact and group IPv6 clients by their canonical /64."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return value
    if isinstance(address, ipaddress.IPv6Address):
        return str(ipaddress.ip_network((address, 64), strict=False))
    return str(address)


def _bucket_key(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{namespace}\0{value}".encode()).hexdigest()


def _database_error_response(error: SQLAlchemyError) -> HTTPException:
    """Translate storage failures without ever bypassing abuse protection."""
    original = getattr(error, "orig", None)
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    if sqlstate == _UNDEFINED_TABLE_SQLSTATE:
        logger.exception(
            "Rate-limit schema is missing; run `alembic upgrade head` before "
            "starting the API"
        )
        return HTTPException(
            status_code=503,
            detail=_UNINITIALIZED_DETAIL,
            headers={"Retry-After": str(_SCHEMA_RETRY_SECONDS)},
        )
    logger.exception("Rate-limit database operation failed")
    return HTTPException(
        status_code=503,
        detail=_UNAVAILABLE_DETAIL,
        headers={"Retry-After": str(_TRANSIENT_RETRY_SECONDS)},
    )


def _consume(namespace: str, value: str, window: int) -> tuple[int, datetime]:
    now = datetime.now(UTC)
    params = {
        "key": _bucket_key(namespace, value),
        "now": now,
        "cutoff": now - timedelta(seconds=window),
        "retention_cutoff": now - _RETENTION,
    }
    try:
        with Session(engine) as session:
            row = session.execute(  # ty: ignore[deprecated] -- raw SQL returns Row
                _UPDATE_ACTIVE_SQL, params
            ).one_or_none()
            if row is None:
                # Serialize only new active-key admission across workers. The
                # recheck handles a concurrent insert of this same key.
                session.execute(  # ty: ignore[deprecated] -- raw cleanup SQL
                    sql_text("SELECT pg_advisory_xact_lock(:lock_id)"),
                    {"lock_id": _ADMISSION_LOCK_ID},
                )
                session.execute(  # ty: ignore[deprecated] -- raw cleanup SQL
                    sql_text(
                        "DELETE FROM rate_limit_bucket "
                        "WHERE updated_at < :retention_cutoff"
                    ),
                    params,
                )
                row = session.execute(  # ty: ignore[deprecated] -- raw SQL Row
                    _UPDATE_ACTIVE_SQL, params
                ).one_or_none()
                if row is None:
                    active_count = session.execute(  # ty: ignore[deprecated]
                        sql_text(
                            "SELECT count(*) FROM rate_limit_bucket "
                            "WHERE updated_at >= :retention_cutoff"
                        ),
                        params,
                    ).one()[0]
                    if int(active_count) >= settings.RATE_LIMIT_MAX_ACTIVE_BUCKETS:
                        raise HTTPException(
                            status_code=503,
                            detail="请求保护服务容量已满，请稍后重试",
                            headers={"Retry-After": "60"},
                        )
                    row = session.execute(  # ty: ignore[deprecated] -- raw SQL Row
                        _INSERT_SQL, params
                    ).one()
            session.commit()
            return int(row[0]), row[1]
    except SQLAlchemyError as error:
        raise _database_error_response(error) from error


def reset() -> None:
    """Clear shared buckets (test-only helper)."""
    try:
        with Session(engine) as session:
            session.execute(  # ty: ignore[deprecated] -- raw test cleanup SQL
                sql_text("DELETE FROM rate_limit_bucket")
            )
            session.commit()
    except SQLAlchemyError:
        # The test/bootstrap database may not have applied the new migration yet.
        pass


def rate_limit(limit: int, window: int = 60) -> Callable[[Request], None]:
    """Allow ``limit`` requests per route/client fixed window."""

    def dependency(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        route = request.scope.get("route")
        path = getattr(route, "path", None) or request.url.path
        identity = _rate_limit_identity(client_ip(request))
        count, started_at = _consume(path, identity, window)
        if count > limit:
            elapsed = (datetime.now(UTC) - started_at).total_seconds()
            retry_after = max(1, math.ceil(window - elapsed))
            raise HTTPException(
                status_code=429,
                detail=f"请求过于频繁，请稍后再试（{window} 秒内最多 {limit} 次）",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency


def recipient_send_cooldown(email: str, window: int = 60) -> bool:
    """Coordinate recipient mail cooldowns across all worker processes."""
    if not settings.RATE_LIMIT_ENABLED:
        return True
    count, _ = _consume("recipient-send", email.strip().lower(), window)
    return count == 1
