from __future__ import annotations

from datetime import UTC, datetime

import pytest

from xtr_rate_limiter import FixedWindowLimiter, InMemoryStorage, InvalidArgumentError
from xtr_rate_limiter._interval import Interval
from xtr_rate_limiter._lock import LocalLock


def test_a_calendar_needs_an_interval_of_a_month_or_more() -> None:
    with pytest.raises(InvalidArgumentError, match="at least one month"):
        _ = FixedWindowLimiter(
            "f",
            1,
            Interval(days=1),
            InMemoryStorage(),
            LocalLock("f"),
            anchor_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_a_limit_must_accept_something() -> None:
    with pytest.raises(InvalidArgumentError):
        _ = FixedWindowLimiter("f", 0, Interval(seconds=1), InMemoryStorage(), LocalLock("f"))
