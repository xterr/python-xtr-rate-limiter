from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from xtr_lock import LockFactory
from xtr_lock.store import InMemoryStore

from xtr_rate_limiter import (
    FixedWindowLimiter,
    InMemoryStorage,
    InvalidArgumentError,
    LimiterConfig,
    NoLimiter,
    Rate,
    RateLimiterFactory,
    SlidingWindowLimiter,
    TokenBucketLimiter,
)

if TYPE_CHECKING:
    from xtr_clock import MockClock

pytestmark = pytest.mark.anyio


def test_a_compound_config_is_not_a_factory_config() -> None:
    with pytest.raises(InvalidArgumentError):
        _ = RateLimiterFactory("x", LimiterConfig("compound", limiters=["a"]), InMemoryStorage())


@pytest.mark.parametrize(
    ("config", "limiter"),
    [
        (LimiterConfig("fixed_window", limit=1, interval="1 minute"), FixedWindowLimiter),
        (LimiterConfig("sliding_window", limit=1, interval="1 minute"), SlidingWindowLimiter),
        (LimiterConfig("token_bucket", limit=1, rate=Rate.per_minute()), TokenBucketLimiter),
        (LimiterConfig("no_limit"), NoLimiter),
    ],
)
def test_it_builds_the_limiter_of_the_policy(config: LimiterConfig, limiter: type) -> None:
    assert isinstance(RateLimiterFactory("x", config, InMemoryStorage()).create("a"), limiter)


async def test_concurrent_hits_on_one_key_are_never_granted_the_same_token(
    clock: MockClock,
) -> None:
    config = LimiterConfig("fixed_window", limit=5, interval="1 minute")
    factory = RateLimiterFactory("api", config, InMemoryStorage(clock), clock=clock)

    limits = await asyncio.gather(*(factory.create("a").consume() for _ in range(20)))

    assert sum(limit.is_accepted() for limit in limits) == 5


async def test_a_lock_factory_guards_each_change(clock: MockClock) -> None:
    config = LimiterConfig("token_bucket", limit=3, rate=Rate.per_minute())
    factory = RateLimiterFactory(
        "api", config, InMemoryStorage(clock), LockFactory(InMemoryStore()), clock=clock
    )

    limits = await asyncio.gather(*(factory.create("a").consume() for _ in range(6)))

    assert sum(limit.is_accepted() for limit in limits) == 3
