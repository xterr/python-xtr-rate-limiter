from __future__ import annotations

from typing import TYPE_CHECKING

from xtr_rate_limiter import RateLimit, RateLimiterError, RateLimitExceededError
from xtr_rate_limiter._time import instant

if TYPE_CHECKING:
    from xtr_clock import MockClock


def test_it_reads_through_to_the_limit(clock: MockClock) -> None:
    limit = RateLimit(3, instant(60), accepted=False, limit=5, clock=clock)

    error = RateLimitExceededError(limit)

    assert (error.remaining_tokens, error.limit, error.retry_after) == (3, 5, limit.retry_after)
    assert isinstance(error, RateLimiterError)
