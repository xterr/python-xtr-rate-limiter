"""A reservation would have to wait longer than its caller agreed to."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .rate_limiter_error import RateLimiterError

if TYPE_CHECKING:
    from xtr_rate_limiter.rate_limit import RateLimit

__all__ = ["MaxWaitDurationExceededError"]


class MaxWaitDurationExceededError(RateLimiterError):
    """A reservation would have to wait longer than its caller agreed to.

    Nothing was reserved: the limiter's state is left as it was.

    Attributes:
        wait_duration: The seconds the tokens would have taken to be free.
        max_time: The seconds the caller agreed to wait.
        rate_limit: The limit as it stands, rejected.
    """

    wait_duration: float
    max_time: float
    rate_limit: RateLimit

    def __init__(self, wait_duration: float, max_time: float, rate_limit: RateLimit) -> None:
        """Record how long the wait would have been, and the limit it was measured against."""
        self.wait_duration = wait_duration
        self.max_time = max_time
        self.rate_limit = rate_limit
        super().__init__(
            f"The rate limiter wait time ({wait_duration:g} seconds) is longer than "
            f"the provided maximum time ({max_time:g} seconds).",
        )
