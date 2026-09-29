"""An interval could not be read, or is not long enough to count anything in."""

from __future__ import annotations

from .invalid_argument_error import InvalidArgumentError

__all__ = ["InvalidIntervalError"]


class InvalidIntervalError(InvalidArgumentError):
    """An interval could not be read, or is not long enough to count anything in.

    Attributes:
        interval: The interval as it was given.
    """

    interval: object

    def __init__(self, interval: object, reason: str) -> None:
        """Record the interval and what is wrong with it."""
        self.interval = interval
        super().__init__(f"Invalid interval {interval!r}: {reason}")
