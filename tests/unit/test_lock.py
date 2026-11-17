from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from tests.support.yielding_storage import YieldingStorage
from xtr_rate_limiter import LimiterConfig, RateLimiterFactory
from xtr_rate_limiter._lock import LocalLock, lock_for

if TYPE_CHECKING:
    from xtr_rate_limiter._lock import LimiterLock


@pytest.mark.anyio
async def test_limiters_of_one_id_share_their_lock() -> None:
    first = LocalLock("a")
    second = lock_for("a", None)
    other = LocalLock("b")
    entered: list[str] = []

    async def enter(lock: LimiterLock, name: str) -> None:
        async with lock.hold():
            entered.append(name)

    async with first.hold():
        waiting = asyncio.create_task(enter(second, "second"))
        await enter(other, "other")
        await asyncio.sleep(0)
        assert entered == ["other"]

    await waiting
    assert entered == ["other", "second"]


def test_a_limiter_is_usable_from_a_second_event_loop() -> None:
    limiter = RateLimiterFactory(
        "loops",
        LimiterConfig("fixed_window", limit=100, interval="1 minute"),
        YieldingStorage(),
    ).create("k")

    async def contend() -> int:
        answers = await asyncio.gather(*(limiter.consume() for _ in range(5)))
        return sum(answer.is_accepted() for answer in answers)

    assert asyncio.run(contend()) == 5
    assert asyncio.run(contend()) == 5
