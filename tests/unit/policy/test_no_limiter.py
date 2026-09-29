from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from xtr_rate_limiter import NoLimiter

if TYPE_CHECKING:
    from xtr_clock import MockClock

pytestmark = pytest.mark.anyio


async def test_it_accepts_everything_at_once(clock: MockClock) -> None:
    limiter = NoLimiter(clock)

    limit = await limiter.consume(10_000)
    reservation = await limiter.reserve(10_000)
    await limiter.reset()

    assert limit.is_accepted()
    assert limit.remaining_tokens == limit.limit == sys.maxsize
    assert limit.reset_at is None
    assert reservation.time_to_act == clock.now().timestamp()
