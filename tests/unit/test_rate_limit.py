from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from xtr_rate_limiter import RateLimit, RateLimitExceededError
from xtr_rate_limiter._time import instant

if TYPE_CHECKING:
    from xtr_clock import MockClock

pytestmark = pytest.mark.anyio


def _limit(clock: MockClock, *, accepted: bool, retry_in: float = 0) -> RateLimit:
    now = clock.now().timestamp()
    return RateLimit(3, instant(now + retry_in), accepted=accepted, limit=5, clock=clock)


async def test_waiting_moves_the_clock_to_the_retry(clock: MockClock) -> None:
    start = clock.now().timestamp()

    await _limit(clock, accepted=False, retry_in=30).wait()

    assert clock.now().timestamp() == pytest.approx(start + 30)


def test_an_accepted_limit_is_returned(clock: MockClock) -> None:
    accepted = _limit(clock, accepted=True)

    assert accepted.ensure_accepted() is accepted


def test_a_refused_limit_raises_with_itself(clock: MockClock) -> None:
    refused = _limit(clock, accepted=False, retry_in=5)

    with pytest.raises(RateLimitExceededError) as raised:
        _ = refused.ensure_accepted()

    assert raised.value.rate_limit is refused


def test_it_shows_its_state(clock: MockClock) -> None:
    limit = _limit(clock, accepted=False)

    assert limit.reset_at is None
    assert "RateLimit(remaining_tokens=3" in repr(limit)
