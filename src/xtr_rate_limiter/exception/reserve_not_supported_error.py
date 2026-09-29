"""A limiter was asked to reserve, which it cannot do."""

from __future__ import annotations

from .rate_limiter_error import RateLimiterError

__all__ = ["ReserveNotSupportedError"]


class ReserveNotSupportedError(RateLimiterError):
    """A limiter was asked to reserve, which it cannot do.

    A compound limiter answers only :meth:`consume`: reserving on several
    limiters would book tokens on some of them while another refuses.

    Attributes:
        limiter: The name of the limiter's class.
    """

    limiter: str

    def __init__(self, limiter: str) -> None:
        """Record which limiter refused."""
        self.limiter = limiter
        super().__init__(f'Reserving tokens is not supported by "{limiter}".')
