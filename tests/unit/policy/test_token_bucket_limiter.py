from __future__ import annotations

import pytest

from xtr_rate_limiter import InMemoryStorage, InvalidArgumentError, Rate, TokenBucketLimiter
from xtr_rate_limiter._lock import LocalLock


def test_a_burst_must_hold_something() -> None:
    with pytest.raises(InvalidArgumentError):
        _ = TokenBucketLimiter("t", 0, Rate.per_second(), InMemoryStorage(), LocalLock("t"))
