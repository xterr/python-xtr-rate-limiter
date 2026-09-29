"""How long a window lasts, or a refill takes: read once, measured when needed.

An interval is kept in the three units a calendar moves by — months, days,
and elapsed seconds — because "1 month" is not a number of seconds until it
is known which month it starts in. :meth:`Interval.seconds_from` answers
that for a given instant; :meth:`Interval.after` and :meth:`Interval.before`
step a date along a calendar, keeping its wall clock across a clock change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, TypeAlias, final

from xtr_clock import shift_calendar

from xtr_rate_limiter.exception import InvalidIntervalError

__all__ = ["Interval", "IntervalLike"]

IntervalLike: TypeAlias = str | timedelta
"""An interval as it is written: ``"15 minutes"``, ``"1 hour 30 minutes"``, or a duration."""

_TERM: Final = re.compile(
    r"\s*(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>second|minute|hour|day|week|month|year)s?\s*",
    re.IGNORECASE,
)

_SECONDS: Final = {"second": 1, "minute": 60, "hour": 3600}
_DAYS: Final = {"day": 1, "week": 7}
_MONTHS: Final = {"month": 1, "year": 12}


@final
@dataclass(frozen=True, slots=True)
class Interval:
    """A span of calendar months, calendar days and elapsed seconds.

    Attributes:
        months: Whole calendar months, a year being twelve.
        days: Whole calendar days, a week being seven.
        seconds: Elapsed seconds, hours and minutes included.
    """

    months: int = 0
    days: int = 0
    seconds: float = 0.0

    @classmethod
    def parse(cls, value: IntervalLike) -> Interval:
        """Read ``value``: a number and a unit, repeated, or a :class:`~datetime.timedelta`.

        The units are ``second``, ``minute``, ``hour``, ``day``, ``week``,
        ``month`` and ``year``, each also plural. Days, weeks, months and
        years must be whole.

        Raises:
            InvalidIntervalError: When ``value`` cannot be read, or is not
                longer than nothing.
        """
        if isinstance(value, timedelta):
            return cls._checked(cls(seconds=value.total_seconds()), value)
        if not isinstance(value, str):  # pyright: ignore[reportUnnecessaryIsInstance] -- configs are written by hand; the annotation is not enforced
            raise InvalidIntervalError(value, "expected a string or a timedelta")  # pyright: ignore[reportUnreachable] -- as above

        months = days = 0
        seconds = 0.0
        position = 0
        for term in _TERM.finditer(value):
            if term.start() != position:
                break
            position = term.end()
            amount = float(term["amount"])
            unit = term["unit"].lower()
            if unit in _SECONDS:
                seconds += amount * _SECONDS[unit]
                continue
            if not amount.is_integer():
                raise InvalidIntervalError(value, f"a number of {unit}s must be whole")
            if unit in _DAYS:
                days += int(amount) * _DAYS[unit]
            else:
                months += int(amount) * _MONTHS[unit]
        if position != len(value) or not value.strip():
            raise InvalidIntervalError(
                value,
                'expected a number followed by "second", "minute", "hour", "day", "week", '
                '"month" or "year", such as "15 minutes"',
            )

        return cls._checked(cls(months, days, seconds), value)

    def after(self, moment: datetime) -> datetime:
        """Return ``moment`` moved forward by this interval."""
        shifted = shift_calendar(moment, months=self.months, days=self.days)
        return shifted + timedelta(seconds=self.seconds)

    def before(self, moment: datetime) -> datetime:
        """Return ``moment`` moved back by this interval."""
        shifted = moment - timedelta(seconds=self.seconds)
        return shift_calendar(shifted, months=-self.months, days=-self.days)

    def seconds_from(self, timestamp: float) -> float:
        """Return how many seconds this interval lasts when it starts at ``timestamp``.

        Counted in UTC, so a day is always 86 400 seconds and only months
        vary in length.
        """
        start = datetime.fromtimestamp(timestamp, UTC)
        return (self.after(start) - start).total_seconds()

    def period_around(self, anchor: datetime, moment: datetime) -> tuple[datetime, datetime]:
        """Return the period, one of this interval's steps from ``anchor``, that holds ``moment``.

        Every boundary is counted from ``anchor`` itself rather than from the
        boundary before it, so a month anchored on the 31st comes back to the
        31st whenever a month has one.
        """
        step = 0
        while self._boundary(anchor, step + 1) <= moment:
            step += 1
        while self._boundary(anchor, step) > moment:
            step -= 1
        return self._boundary(anchor, step), self._boundary(anchor, step + 1)

    def _boundary(self, anchor: datetime, step: int) -> datetime:
        shifted = shift_calendar(anchor, months=self.months * step, days=self.days * step)
        return shifted + timedelta(seconds=self.seconds * step)

    @classmethod
    def _checked(cls, interval: Interval, value: object) -> Interval:
        if interval.months < 0 or interval.days < 0 or interval.seconds < 0:
            raise InvalidIntervalError(value, "an interval cannot be negative")
        if not (interval.months or interval.days or interval.seconds):
            raise InvalidIntervalError(value, "an interval must last longer than nothing")
        return interval
