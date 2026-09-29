from __future__ import annotations

from typing import TYPE_CHECKING

from xtr_rate_limiter import MaxWaitDurationExceededError, RateLimit, RateLimiterError
from xtr_rate_limiter._time import instant

if TYPE_CHECKING:
    from xtr_clock import MockClock


def test_it_carries_the_wait_the_maximum_and_the_limit(clock: MockClock) -> None:
    limit = RateLimit(0, instant(60), accepted=False, limit=1, clock=clock)

    error = MaxWaitDurationExceededError(60, 5, limit)

    assert (error.wait_duration, error.max_time, error.rate_limit) == (60, 5, limit)
    assert "60 seconds" in str(error)
    assert isinstance(error, RateLimiterError)
