"""Redis clients from DSNs, for the bundle to open and the factory to count on."""

from __future__ import annotations

import importlib.util
import sys
from typing import TYPE_CHECKING, Final, TypeGuard

from xtr_rate_limiter.exception import InvalidArgumentError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from redis.asyncio import Redis

__all__ = [
    "DEFAULT_TIMEOUT",
    "REDIS_SCHEMES",
    "create_redis_client",
    "is_redis_client",
    "is_redis_dsn",
    "redis_installed",
]

REDIS_SCHEMES: Final[Mapping[str, str]] = {
    "redis": "redis",
    "rediss": "rediss",
    "valkey": "redis",
    "valkeys": "rediss",
    "unix": "unix",
}
"""Each accepted scheme, and the one the client is given for it."""

DEFAULT_TIMEOUT: Final = 5.0
"""Seconds a client waits to connect, or for a reply, unless the DSN says otherwise."""

_MISSING: Final = 'Counting in Redis needs the Redis client: install "xtr-rate-limiter[redis]".'


def is_redis_dsn(dsn: str) -> bool:
    """Tell whether ``dsn`` has one of :data:`REDIS_SCHEMES`, in any case."""
    scheme, separator, _ = dsn.partition(":")
    return bool(separator) and scheme.lower() in REDIS_SCHEMES


def redis_installed() -> bool:
    """Tell whether the Redis client library can be imported, without importing it."""
    return importlib.util.find_spec("redis") is not None


def create_redis_client(dsn: str) -> Redis:
    """Return an asyncio client for ``dsn`` that connects on first use.

    Raises:
        InvalidArgumentError: When the scheme is not a Redis one — naming the
            scheme only, never credentials — or the client library is not
            installed.
    """
    scheme, separator, rest = dsn.partition(":")
    target = REDIS_SCHEMES.get(scheme.lower()) if separator else None
    if target is None:
        raise InvalidArgumentError(
            f'"{scheme}" is not a Redis scheme; expected one of {", ".join(REDIS_SCHEMES)}.',
        )

    try:
        from redis.asyncio import Redis  # noqa: PLC0415 — the redis extra is optional.
    except ImportError as error:  # pragma: no cover — exercised only without the extra.
        raise InvalidArgumentError(_MISSING) from error

    # The keyword arguments are untyped. The DSN's query wins over them.
    return Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        f"{target}:{rest}",
        socket_connect_timeout=DEFAULT_TIMEOUT,
        socket_timeout=DEFAULT_TIMEOUT,
    )


def is_redis_client(connection: object) -> TypeGuard[Redis]:
    """Tell whether ``connection`` is an asyncio Redis client, without importing the library."""
    # Without the client library imported, nothing can be one of its clients.
    if "redis.asyncio" not in sys.modules:
        return False

    from redis.asyncio import Redis as Client  # noqa: PLC0415 — the redis extra is optional.

    return isinstance(connection, Client)
