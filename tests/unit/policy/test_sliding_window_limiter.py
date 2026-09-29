from __future__ import annotations

import pytest

from xtr_rate_limiter import InMemoryStorage, InvalidArgumentError, SlidingWindowLimiter
from xtr_rate_limiter._interval import Interval
from xtr_rate_limiter._lock import LocalLock


def test_a_limit_must_accept_something() -> None:
    with pytest.raises(InvalidArgumentError):
        _ = SlidingWindowLimiter("s", 0, Interval(seconds=1), InMemoryStorage(), LocalLock("s"))
