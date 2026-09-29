from __future__ import annotations

from xtr_rate_limiter import InvalidArgumentError, InvalidIntervalError


def test_it_names_the_interval_and_is_an_invalid_argument() -> None:
    error = InvalidIntervalError("soon", "unreadable")

    assert error.interval == "soon"
    assert "soon" in error.reason
    assert isinstance(error, InvalidArgumentError)
