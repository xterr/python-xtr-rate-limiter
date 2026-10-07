from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from xtr_cache.adapter import ArrayAdapter

from xtr_rate_limiter import (
    CacheStorage,
    InMemoryStorage,
    InvalidArgumentError,
    Rate,
    TokenBucketLimiter,
)
from xtr_rate_limiter._lock import LocalLock
from xtr_rate_limiter.policy.token_bucket import TokenBucket

if TYPE_CHECKING:
    from xtr_clock import MockClock


def test_a_burst_must_hold_something() -> None:
    with pytest.raises(InvalidArgumentError):
        _ = TokenBucketLimiter("t", 0, Rate.per_second(), InMemoryStorage(), LocalLock("t"))


@pytest.mark.anyio
async def test_a_peek_leaves_the_bucket_as_it_found_it(clock: MockClock) -> None:
    # A pool handing back the object it holds shows any change a peek makes.
    storage = CacheStorage(ArrayAdapter(store_serialized=False, clock=clock))
    limiter = TokenBucketLimiter("t", 2, Rate("10 seconds"), storage, LocalLock("t"), clock=clock)
    start = clock.now().timestamp()
    _ = await limiter.consume(2)

    clock.sleep(15)
    _ = await limiter.consume(0)

    kept = await storage.fetch("t")
    assert isinstance(kept, TokenBucket)
    assert kept.timer == start
