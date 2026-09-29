"""Every way a limit can be counted, behind one factory-making function."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from xtr_cache.adapter import ArrayAdapter

from xtr_rate_limiter import CacheStorage, InMemoryStorage, RateLimiterFactory
from xtr_rate_limiter.redis import RedisRateLimiterFactory

if TYPE_CHECKING:
    from collections.abc import Callable

    from fakeredis import FakeAsyncRedis
    from xtr_clock import MockClock

    from xtr_rate_limiter import LimiterConfig, RateLimiterFactoryInterface

__all__ = ["BACKENDS", "make_factory"]

BACKENDS: Final = ("memory", "cache", "redis")


def make_factory(
    backend: str, clock: MockClock, redis_client: FakeAsyncRedis
) -> Callable[[LimiterConfig], RateLimiterFactoryInterface]:
    """Return a function building a factory for a config, counting on ``backend``."""
    if backend == "redis":
        return lambda config: RedisRateLimiterFactory(
            "test", config, redis_client, clock=clock, server_time=False
        )
    storage = (
        InMemoryStorage(clock) if backend == "memory" else CacheStorage(ArrayAdapter(clock=clock))
    )
    return lambda config: RateLimiterFactory("test", config, storage, clock=clock)
