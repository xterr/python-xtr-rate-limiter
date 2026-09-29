from __future__ import annotations

from datetime import UTC, datetime

import pytest

from xtr_rate_limiter import InvalidArgumentError, InvalidIntervalError, Rate


def test_a_rate_refuses_nothing_to_add_and_an_unreadable_interval() -> None:
    with pytest.raises(InvalidArgumentError):
        _ = Rate("1 second", amount=0)
    with pytest.raises(InvalidIntervalError):
        _ = Rate("soon")


@pytest.mark.parametrize(
    ("rate", "seconds"),
    [
        (Rate.per_second(), 1),
        (Rate.per_minute(), 60),
        (Rate.per_hour(), 3600),
        (Rate.per_day(), 86_400),
        (Rate.per_month(), 31 * 86_400),
        (Rate.per_year(), 365 * 86_400),
    ],
)
def test_a_rate_cycles_as_its_interval(rate: Rate, seconds: int) -> None:
    assert rate.cycle_from(datetime(2026, 1, 1, tzinfo=UTC).timestamp()) == seconds
