from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from xtr_cache.adapter import ArrayAdapter

from xtr_rate_limiter import CacheStorage
from xtr_rate_limiter.policy.window import Window

if TYPE_CHECKING:
    from xtr_clock import MockClock

pytestmark = pytest.mark.anyio


async def test_a_state_lives_in_the_pool_under_a_hashed_key_until_it_expires(
    clock: MockClock,
) -> None:
    pool = ArrayAdapter(clock=clock)
    storage = CacheStorage(pool)
    await storage.save(Window("api-user@example.com:1", 60, 5, clock.now().timestamp()))

    assert isinstance(await storage.fetch("api-user@example.com:1"), Window)

    clock.sleep(61)
    assert await storage.fetch("api-user@example.com:1") is None


async def test_something_else_under_the_key_is_no_state(clock: MockClock) -> None:
    pool = ArrayAdapter(clock=clock)
    storage = CacheStorage(pool)
    await storage.save(Window("w", 60, 5, clock.now().timestamp()))

    await storage.delete("w")

    assert await storage.fetch("w") is None
