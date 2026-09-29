"""How fast a token bucket refills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import final

from xtr_rate_limiter._interval import Interval, IntervalLike
from xtr_rate_limiter.exception import InvalidArgumentError

__all__ = ["Rate"]


@final
@dataclass(frozen=True, slots=True)
class Rate:
    """``amount`` tokens back in the bucket every ``interval``.

    ```python
    Rate("10 seconds", amount=5)
    Rate.per_minute(30)
    ```

    Attributes:
        interval: How often the bucket is topped up: ``"15 minutes"``, or a
            :class:`~datetime.timedelta`.
        amount: How many tokens each top-up adds.
    """

    interval: IntervalLike
    amount: int = 1

    def __post_init__(self) -> None:
        """Refuse an interval that cannot be read, or an amount below one.

        Raises:
            InvalidIntervalError: When the interval cannot be read.
            InvalidArgumentError: When the amount is below one.
        """
        _ = Interval.parse(self.interval)
        if self.amount < 1:
            raise InvalidArgumentError(f"A rate must add at least one token, got {self.amount}.")

    @classmethod
    def per_second(cls, amount: int = 1) -> Rate:
        """Return ``amount`` tokens a second."""
        return cls("1 second", amount)

    @classmethod
    def per_minute(cls, amount: int = 1) -> Rate:
        """Return ``amount`` tokens a minute."""
        return cls("1 minute", amount)

    @classmethod
    def per_hour(cls, amount: int = 1) -> Rate:
        """Return ``amount`` tokens an hour."""
        return cls("1 hour", amount)

    @classmethod
    def per_day(cls, amount: int = 1) -> Rate:
        """Return ``amount`` tokens a day."""
        return cls("1 day", amount)

    @classmethod
    def per_month(cls, amount: int = 1) -> Rate:
        """Return ``amount`` tokens a month."""
        return cls("1 month", amount)

    @classmethod
    def per_year(cls, amount: int = 1) -> Rate:
        """Return ``amount`` tokens a year."""
        return cls("1 year", amount)

    def cycle_from(self, timestamp: float) -> float:
        """Return how many seconds one top-up takes, starting at ``timestamp``."""
        return Interval.parse(self.interval).seconds_from(timestamp)
