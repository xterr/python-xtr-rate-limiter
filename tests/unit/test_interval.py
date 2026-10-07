from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from xtr_rate_limiter import InvalidArgumentError, InvalidIntervalError
from xtr_rate_limiter._interval import Interval


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("15 minutes", Interval(seconds=900)),
        ("1 hour 30 minutes", Interval(seconds=5400)),
        ("2 weeks", Interval(days=14)),
        ("1 year 1 month", Interval(months=13)),
        ("0.5 seconds", Interval(seconds=0.5)),
    ],
)
def test_it_reads_units(text: str, expected: Interval) -> None:
    assert Interval.parse(text) == expected


def test_it_reads_a_timedelta() -> None:
    assert Interval.parse(timedelta(minutes=2)) == Interval(seconds=120)


@pytest.mark.parametrize("text", ["", "soon", "5", "1.5 days", "1 minute and more", "0 seconds"])
def test_it_refuses_what_it_cannot_read(text: str) -> None:
    with pytest.raises(InvalidIntervalError):
        _ = Interval.parse(text)


def test_it_refuses_a_negative_timedelta_and_a_foreign_type() -> None:
    with pytest.raises(InvalidIntervalError):
        _ = Interval.parse(timedelta(seconds=-1))
    with pytest.raises(InvalidIntervalError):
        _ = Interval.parse(5)  # pyright: ignore[reportArgumentType]  # ty: ignore[invalid-argument-type]


def test_a_month_lasts_as_long_as_the_month_it_starts_in() -> None:
    february = datetime(2026, 2, 1, tzinfo=UTC).timestamp()

    assert Interval(months=1).seconds_from(february) == 28 * 86_400


def test_it_steps_forward_and_back() -> None:
    moment = datetime(2026, 1, 31, 12, tzinfo=UTC)
    interval = Interval(months=1, days=1, seconds=60)

    assert interval.after(moment) == datetime(2026, 3, 1, 12, 1, tzinfo=UTC)
    assert interval.before(datetime(2026, 3, 1, 12, 1, tzinfo=UTC)) == datetime(
        2026, 1, 31, 12, tzinfo=UTC
    )


def test_a_period_counts_every_boundary_from_the_anchor() -> None:
    anchor = datetime(2026, 1, 31, tzinfo=UTC)

    start, end = Interval(months=1).period_around(anchor, datetime(2026, 3, 30, tzinfo=UTC))
    before, after = Interval(months=1).period_around(anchor, datetime(2025, 12, 1, tzinfo=UTC))

    assert (start, end) == (datetime(2026, 2, 28, tzinfo=UTC), datetime(2026, 3, 31, tzinfo=UTC))
    assert (before, after) == (
        datetime(2025, 11, 30, tzinfo=UTC),
        datetime(2025, 12, 31, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("interval", "anchor", "moment", "expected"),
    [
        (
            Interval(months=1),
            datetime(1970, 1, 1, tzinfo=UTC),
            datetime(2026, 3, 30, tzinfo=UTC),
            (datetime(2026, 3, 1, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC)),
        ),
        (
            Interval(months=1),
            datetime(2270, 1, 1, tzinfo=UTC),
            datetime(2026, 3, 30, tzinfo=UTC),
            (datetime(2026, 3, 1, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC)),
        ),
        (
            Interval(days=1),
            datetime(1970, 1, 1, tzinfo=UTC),
            datetime(2026, 3, 30, 12, tzinfo=UTC),
            (datetime(2026, 3, 30, tzinfo=UTC), datetime(2026, 3, 31, tzinfo=UTC)),
        ),
        (
            Interval(seconds=900),
            datetime(1970, 1, 1, tzinfo=UTC),
            datetime(2026, 3, 30, 12, 20, tzinfo=UTC),
            (
                datetime(2026, 3, 30, 12, 15, tzinfo=UTC),
                datetime(2026, 3, 30, 12, 30, tzinfo=UTC),
            ),
        ),
    ],
)
def test_a_period_is_found_whatever_the_distance_to_the_anchor(
    interval: Interval,
    anchor: datetime,
    moment: datetime,
    expected: tuple[datetime, datetime],
) -> None:
    assert interval.period_around(anchor, moment) == expected


def test_a_period_of_nothing_is_refused_rather_than_divided_by() -> None:
    with pytest.raises(InvalidArgumentError):
        _ = Interval().period_around(
            datetime(1970, 1, 1, tzinfo=UTC), datetime(2026, 3, 30, tzinfo=UTC)
        )
