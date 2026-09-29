from __future__ import annotations

from typing import TYPE_CHECKING

from xtr_rate_limiter import RateLimit, RateLimitExceededEvent
from xtr_rate_limiter._time import instant

if TYPE_CHECKING:
    from xtr_clock import MockClock


def test_it_carries_the_limit_the_name_and_the_key_and_can_be_stopped(clock: MockClock) -> None:
    limit = RateLimit(0, instant(0), accepted=False, limit=1, clock=clock)
    event = RateLimitExceededEvent(limit, "login", "alice")

    event.stop_propagation()

    assert (event.rate_limit, event.limiter_name, event.key) == (limit, "login", "alice")
    assert event.is_propagation_stopped()
