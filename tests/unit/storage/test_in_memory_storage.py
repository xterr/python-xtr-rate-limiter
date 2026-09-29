from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from xtr_rate_limiter import InMemoryStorage
from xtr_rate_limiter.policy.window import Window

if TYPE_CHECKING:
    from xtr_clock import MockClock

pytestmark = pytest.mark.anyio


async def test_it_hands_back_a_copy_until_the_state_expires(clock: MockClock) -> None:
    storage = InMemoryStorage(clock)
    now = clock.now().timestamp()
    window = Window("w", 60, 5, now)
    window.add(1, now)
    await storage.save(window)

    fetched = await storage.fetch("w")
    assert isinstance(fetched, Window)
    assert fetched is not window
    assert fetched.hit_count == 1

    clock.sleep(61)
    assert await storage.fetch("w") is None


async def test_expired_states_are_swept_out_without_being_read(clock: MockClock) -> None:
    storage = InMemoryStorage(clock)
    for index in range(999):
        await storage.save(Window(f"old-{index}", 60, 5, clock.now().timestamp()))

    clock.sleep(61)
    await storage.save(Window("fresh", 60, 5, clock.now().timestamp()))

    assert len(storage) == 1
    assert await storage.fetch("fresh") is not None


async def test_it_deletes_and_misses(clock: MockClock) -> None:
    storage = InMemoryStorage(clock)
    await storage.save(Window("w", 60, 5, clock.now().timestamp()))

    await storage.delete("w")
    await storage.delete("never")

    assert await storage.fetch("w") is None
