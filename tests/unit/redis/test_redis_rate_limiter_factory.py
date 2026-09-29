from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from xtr_rate_limiter import InvalidArgumentError, LimiterConfig, NoLimiter
from xtr_rate_limiter.redis import RedisLimiter, RedisRateLimiterFactory

if TYPE_CHECKING:
    from fakeredis import FakeAsyncRedis

pytestmark = pytest.mark.anyio


async def test_it_counts_by_the_server_clock_and_keeps_one_hash_per_key(
    redis_client: FakeAsyncRedis,
) -> None:
    config = LimiterConfig("fixed_window", limit=2, interval="1 minute")
    factory = RedisRateLimiterFactory("api", config, redis_client, prefix="app:")

    limiter = factory.create("alice")
    limit = await limiter.consume()

    assert isinstance(limiter, RedisLimiter)
    assert limit.remaining_tokens == 1
    assert await redis_client.hget("app:api-alice", "hits") == b"1"
    assert 0 < await redis_client.pttl("app:api-alice") <= 60_000


async def test_no_limit_needs_no_server(redis_client: FakeAsyncRedis) -> None:
    factory = RedisRateLimiterFactory("open", LimiterConfig("no_limit"), redis_client)

    assert isinstance(factory.create("a"), NoLimiter)


async def test_a_compound_config_is_not_a_factory_config(redis_client: FakeAsyncRedis) -> None:
    with pytest.raises(InvalidArgumentError):
        _ = RedisRateLimiterFactory("x", LimiterConfig("compound", limiters=["a"]), redis_client)
