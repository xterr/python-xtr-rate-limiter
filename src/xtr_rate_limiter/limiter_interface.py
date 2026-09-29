"""What a limiter for one key answers to."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .rate_limit import RateLimit
    from .reservation import Reservation

__all__ = ["LimiterInterface"]


@runtime_checkable
class LimiterInterface(Protocol):
    """Counts the hits of one key — one user, one address, one account — against a limit.

    A limiter comes from a
    :class:`~xtr_rate_limiter.rate_limiter_factory_interface.RateLimiterFactoryInterface`,
    one per key. Two ways to spend tokens:

    - :meth:`consume` decides now: the tokens are granted, or they are not
      and nothing is spent.
    - :meth:`reserve` books the tokens for the moment they become available,
      which may lie ahead, and says when that is.

    Spending zero tokens changes nothing and reports the limit as it stands.
    """

    async def reserve(self, tokens: int = 1, max_time: float | None = None) -> Reservation:
        """Book ``tokens`` for the moment they become available.

        Args:
            tokens: How many tokens to book.
            max_time: The most seconds the caller will wait; any wait when
                ``None``.

        Raises:
            InvalidArgumentError: When ``tokens`` is negative or more than the
                limiter ever holds.
            MaxWaitDurationExceededError: When the wait would be longer than
                ``max_time``; nothing is booked.
            ReserveNotSupportedError: When this limiter cannot reserve.
        """
        ...

    async def consume(self, tokens: int = 1) -> RateLimit:
        """Spend ``tokens`` now if they are available; spend nothing otherwise.

        Raises:
            InvalidArgumentError: When ``tokens`` is negative or more than the
                limiter ever holds.
        """
        ...

    async def reset(self) -> None:
        """Forget every hit counted for this key."""
        ...
