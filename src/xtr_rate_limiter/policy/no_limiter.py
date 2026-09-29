"""A limiter that accepts everything."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, final

from typing_extensions import override
from xtr_clock import Clock

from xtr_rate_limiter._time import instant
from xtr_rate_limiter.limiter_interface import LimiterInterface
from xtr_rate_limiter.rate_limit import RateLimit
from xtr_rate_limiter.reservation import Reservation

if TYPE_CHECKING:
    from xtr_clock import ClockInterface

__all__ = ["NoLimiter"]


@final
class NoLimiter(LimiterInterface):
    """Accepts every hit and keeps nothing.

    For code that expects a limiter where no limit should apply — a limit
    turned off in one environment, a trusted caller.
    """

    __slots__ = ("_clock",)

    def __init__(self, clock: ClockInterface | None = None) -> None:
        """Report instants by ``clock``; the clock in force when ``None``."""
        self._clock: ClockInterface = clock if clock is not None else Clock()

    @override
    async def reserve(self, tokens: int = 1, max_time: float | None = None) -> Reservation:
        """Grant ``tokens`` at once."""
        now = self._clock.now().timestamp()
        return Reservation(now, self._rate_limit(now), clock=self._clock)

    @override
    async def consume(self, tokens: int = 1) -> RateLimit:
        """Grant ``tokens``."""
        return self._rate_limit(self._clock.now().timestamp())

    @override
    async def reset(self) -> None:
        """Do nothing: nothing was counted."""

    def _rate_limit(self, now: float) -> RateLimit:
        return RateLimit(
            sys.maxsize, instant(now), accepted=True, limit=sys.maxsize, clock=self._clock
        )
