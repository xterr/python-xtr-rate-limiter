from __future__ import annotations

from xtr_rate_limiter import RateLimiterError, RateLimiterStorageError


def test_it_carries_its_reason_and_derives_from_the_base() -> None:
    error = RateLimiterStorageError("down")

    assert error.reason == "down"
    assert isinstance(error, RateLimiterError)
