from __future__ import annotations

from xtr_rate_limiter import RateLimiterError, ReserveNotSupportedError


def test_it_names_the_limiter() -> None:
    error = ReserveNotSupportedError("CompoundLimiter")

    assert error.limiter == "CompoundLimiter"
    assert isinstance(error, RateLimiterError)
