"""The application's own Redis client and storage, which it opens and closes."""

from __future__ import annotations

from collections.abc import AsyncIterator  # noqa: TC003 — the container reads the annotation.

from fakeredis import FakeAsyncRedis, FakeServer
from redis.asyncio import Redis  # noqa: TC002 — the container reads the annotation.
from xtr_dependency_injection import as_service

from xtr_rate_limiter import InMemoryStorage, StorageInterface

LIMITS = "limits"


@as_service(qualifier=LIMITS)
async def limits_redis() -> AsyncIterator[Redis]:
    # A server of its own, in this process, running the limiters' scripts.
    client = FakeAsyncRedis(server=FakeServer())
    try:
        yield client
    finally:
        await client.aclose()


@as_service(qualifier=LIMITS)
def limits_storage() -> StorageInterface:
    return InMemoryStorage()
