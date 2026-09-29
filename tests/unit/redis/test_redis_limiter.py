from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from xtr_rate_limiter import LimiterConfig
from xtr_rate_limiter.redis import RedisRateLimiterFactory

if TYPE_CHECKING:
    from fakeredis import FakeAsyncRedis
    from xtr_clock import MockClock

pytestmark = pytest.mark.anyio

_CONFIG = LimiterConfig("fixed_window", limit=2, interval="1 minute")


async def test_a_reset_deletes_the_key(redis_client: FakeAsyncRedis, clock: MockClock) -> None:
    limiter = RedisRateLimiterFactory("api", _CONFIG, redis_client, clock=clock).create("a")
    _ = await limiter.consume(2)

    await limiter.reset()

    assert await redis_client.exists("rate_limiter:api-a") == 0


async def test_it_refuses_tokens_it_could_never_hold(redis_client: FakeAsyncRedis) -> None:
    limiter = RedisRateLimiterFactory("api", _CONFIG, redis_client).create("a")

    with pytest.raises(ValueError, match="negative"):
        _ = await limiter.consume(-1)
    with pytest.raises(ValueError, match="more tokens"):
        _ = await limiter.consume(3)
