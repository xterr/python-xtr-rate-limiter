"""Tokens booked for a moment that may lie ahead, and the wait until it comes."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from typing_extensions import override
from xtr_clock import Clock

if TYPE_CHECKING:
    from xtr_clock import ClockInterface

    from .rate_limit import RateLimit

__all__ = ["Reservation"]


@final
class Reservation:
    """Tokens a limiter has booked, to be used at :attr:`time_to_act`.

    The booking is made when the reservation is: from then on the limiter
    counts those tokens as spent, so later callers are served after this one.

    ```python
    reservation = await limiter.reserve(tokens=1, max_time=5)
    await reservation.wait()
    await call_the_api()
    ```
    """

    __slots__ = ("_clock", "_rate_limit", "_time_to_act")

    def __init__(
        self,
        time_to_act: float,
        rate_limit: RateLimit,
        *,
        clock: ClockInterface | None = None,
    ) -> None:
        """Describe a reservation.

        Args:
            time_to_act: When the tokens may be used, in seconds since the
                epoch.
            rate_limit: The limit as the reservation left it.
            clock: What waiting is measured against; the clock in force when
                ``None``.
        """
        self._time_to_act = time_to_act
        self._rate_limit = rate_limit
        self._clock: ClockInterface = clock if clock is not None else Clock()

    @property
    def time_to_act(self) -> float:
        """When the tokens may be used, in seconds since the epoch."""
        return self._time_to_act

    @property
    def rate_limit(self) -> RateLimit:
        """The limit as the reservation left it."""
        return self._rate_limit

    def wait_duration(self) -> float:
        """Return how many seconds are left until :attr:`time_to_act`; zero once it passed."""
        return max(0.0, self._time_to_act - self._clock.now().timestamp())

    async def wait(self) -> None:
        """Wait until :attr:`time_to_act`, without blocking the event loop."""
        await self._clock.sleep_async(self.wait_duration())

    @override
    def __repr__(self) -> str:
        """Show when the reservation acts."""
        return f"{type(self).__name__}(time_to_act={self._time_to_act!r})"
