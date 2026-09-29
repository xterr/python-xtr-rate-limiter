from __future__ import annotations

from xtr_rate_limiter import InvalidArgumentError, RateLimiterError


def test_it_carries_its_reason_and_derives_from_the_base() -> None:
    error = InvalidArgumentError("bad")

    assert error.reason == "bad"
    assert isinstance(error, RateLimiterError)


def test_it_is_a_value_error() -> None:
    assert isinstance(InvalidArgumentError("bad"), ValueError)
