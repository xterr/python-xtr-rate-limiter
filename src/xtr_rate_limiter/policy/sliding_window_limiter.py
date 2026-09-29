"""Limits hits over a window that slides, smoothing bursts at window boundaries."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, ClassVar, final

from typing_extensions import override
from xtr_clock import Clock

from xtr_rate_limiter._time import instant
from xtr_rate_limiter.exception import MaxWaitDurationExceededError
from xtr_rate_limiter.rate_limit import RateLimit
from xtr_rate_limiter.reservation import Reservation

from ._stored_limiter import StoredLimiter, check_limit, check_tokens
from .sliding_window import SlidingWindow

if TYPE_CHECKING:
    from xtr_clock import ClockInterface

    from xtr_rate_limiter._interval import Interval
    from xtr_rate_limiter._lock import LimiterLock
    from xtr_rate_limiter.storage.storage_interface import StorageInterface

__all__ = ["SlidingWindowLimiter"]


@final
class SlidingWindowLimiter(StoredLimiter):
    """At most ``limit`` hits in any span of ``interval``, as estimated by a sliding window.

    Where a fixed window lets a burst at the end of one window and another at
    the start of the next through together, a sliding window still counts
    the first burst while it lies within the last ``interval``.
    """

    __slots__: ClassVar[tuple[str, ...]] = ("_interval_seconds", "_limit")

    def __init__(  # noqa: PLR0913 — every option past the lock is keyword-only.
        self,
        state_id: str,
        limit: int,
        interval: Interval,
        storage: StorageInterface,
        lock: LimiterLock,
        *,
        clock: ClockInterface | None = None,
    ) -> None:
        """Limit ``state_id`` to ``limit`` hits in any ``interval``.

        Raises:
            InvalidArgumentError: When ``limit`` is below one.
        """
        check_limit(limit)
        resolved: ClockInterface = clock if clock is not None else Clock()
        super().__init__(state_id, storage, lock, resolved)
        self._limit = limit
        self._interval_seconds = interval.seconds_from(resolved.now().timestamp())

    @override
    async def _reserve(self, tokens: int, max_time: float | None) -> Reservation:
        check_tokens(tokens, self._limit, "size")
        now = self._clock.now().timestamp()
        stored = await self._storage.fetch(self._id)
        if not isinstance(stored, SlidingWindow):
            window = SlidingWindow(self._id, self._interval_seconds, now)
        elif stored.is_expired(now):
            window = SlidingWindow.from_previous_window(stored, self._interval_seconds, now)
        else:
            window = stored

        available = self._limit - window.hit_count(now)
        if tokens == 0:
            reset_duration = window.time_for_tokens(self._limit, window.hit_count(now), now)
            retry_after = now if available > 0 else now + reset_duration
            limit = self._rate_limit(window, now, retry_after=retry_after, accepted=True)
            return Reservation(now, limit, clock=self._clock)

        if available >= tokens:
            window.add(tokens)
            retry_after = now
            if available == tokens:
                retry_after += window.time_for_tokens(self._limit, window.hit_count(now), now)
            limit = self._rate_limit(window, now, retry_after=retry_after, accepted=True)
            reservation = Reservation(now, limit, clock=self._clock)
        else:
            wait = window.time_for_tokens(self._limit, tokens, now)
            if max_time is not None and wait > max_time:
                rejected = self._rate_limit(window, now, retry_after=now + wait, accepted=False)
                raise MaxWaitDurationExceededError(wait, max_time, rejected)
            window.add(tokens)
            limit = self._rate_limit(window, now, retry_after=now + wait, accepted=False)
            reservation = Reservation(now + wait, limit, clock=self._clock)

        await self._storage.save(window)
        return reservation

    def _rate_limit(
        self,
        window: SlidingWindow,
        now: float,
        *,
        retry_after: float,
        accepted: bool,
    ) -> RateLimit:
        if not window.hit_count(now):
            reset_at = now
        else:
            # The count falls below one hit strictly after that instant.
            reset_at = math.floor(max(now, window.full_capacity_time(now))) + 1
        return RateLimit(
            self._limit - window.hit_count(now),
            instant(retry_after),
            accepted=accepted,
            limit=self._limit,
            reset_at=instant(reset_at),
            clock=self._clock,
        )
