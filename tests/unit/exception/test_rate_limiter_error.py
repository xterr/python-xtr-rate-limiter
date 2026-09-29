from __future__ import annotations

from xtr_rate_limiter import RateLimiterError


def test_it_is_an_exception() -> None:
    assert issubclass(RateLimiterError, Exception)
