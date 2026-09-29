"""Limits hits per window of fixed length, or per period of a calendar."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, final

from typing_extensions import override
from xtr_clock import Clock

from xtr_rate_limiter._time import instant
from xtr_rate_limiter.exception import InvalidArgumentError, MaxWaitDurationExceededError
from xtr_rate_limiter.rate_limit import RateLimit
from xtr_rate_limiter.reservation import Reservation

from ._stored_limiter import StoredLimiter, check_limit, check_tokens
from .calendar_aligned_window import CalendarAlignedWindow
from .window import Window

if TYPE_CHECKING:
    from datetime import datetime

    from xtr_clock import ClockInterface

    from xtr_rate_limiter._interval import Interval
    from xtr_rate_limiter._lock import LimiterLock
    from xtr_rate_limiter.storage.storage_interface import StorageInterface

__all__ = ["FixedWindowLimiter"]


@final
class FixedWindowLimiter(StoredLimiter):
    """At most ``limit`` hits per window of ``interval``.

    By default a window opens on the first hit and lasts ``interval``. With
    ``anchor_at``, windows follow a calendar instead: every ``interval`` from
    that instant — the first of each month, say — whenever the hits arrive.
    The anchor keeps its zone, so a local midnight stays a local midnight
    across a clock change, and may lie in the past or the future.

    A window counts hits simply, so a burst at the end of one window and
    another at the start of the next can reach twice the limit in a short
    span; a sliding window smooths that out.
    """

    __slots__: ClassVar[tuple[str, ...]] = (
        "_anchor_at",
        "_interval",
        "_interval_seconds",
        "_limit",
    )

    def __init__(  # noqa: PLR0913 — every option past the lock is keyword-only.
        self,
        state_id: str,
        limit: int,
        interval: Interval,
        storage: StorageInterface,
        lock: LimiterLock,
        *,
        anchor_at: datetime | None = None,
        clock: ClockInterface | None = None,
    ) -> None:
        """Limit ``state_id`` to ``limit`` hits per ``interval``.

        Raises:
            InvalidArgumentError: When ``limit`` is below one, or ``anchor_at``
                is given with an interval shorter than a month.
        """
        check_limit(limit)
        if anchor_at is not None and interval.months == 0:
            raise InvalidArgumentError(
                "Aligning a fixed window to a calendar requires an interval of at least one month.",
            )
        resolved: ClockInterface = clock if clock is not None else Clock()
        super().__init__(state_id, storage, lock, resolved)
        self._limit = limit
        self._interval = interval
        self._interval_seconds = interval.seconds_from(resolved.now().timestamp())
        self._anchor_at = anchor_at

    @override
    async def _reserve(self, tokens: int, max_time: float | None) -> Reservation:
        check_tokens(tokens, self._limit, "size")
        moment = self._clock.now()
        now = moment.timestamp()
        window = await self._window(moment, now)

        if tokens == 0:
            wait = window.time_for_tokens(1, now)
            limit = self._rate_limit(window, now, retry_after=now + wait, accepted=True)
            reservation = Reservation(now + wait, limit, clock=self._clock)
        elif self._available(window, now) >= tokens:
            exhausts = self._available(window, now) == tokens
            self._add(window, tokens, now)
            retry_after = now + window.time_for_tokens(1, now) if exhausts else now
            limit = self._rate_limit(window, now, retry_after=retry_after, accepted=True)
            reservation = Reservation(now, limit, clock=self._clock)
        else:
            wait = window.time_for_tokens(tokens, now)
            if max_time is not None and wait > max_time:
                rejected = self._rate_limit(window, now, retry_after=now + wait, accepted=False)
                raise MaxWaitDurationExceededError(wait, max_time, rejected)
            self._add(window, tokens, now)
            limit = self._rate_limit(window, now, retry_after=now + wait, accepted=False)
            reservation = Reservation(now + wait, limit, clock=self._clock)

        if tokens != 0:
            await self._storage.save(window)
        return reservation

    async def _window(self, moment: datetime, now: float) -> Window | CalendarAlignedWindow:
        stored = await self._storage.fetch(self._id)
        if self._anchor_at is not None:
            if isinstance(stored, CalendarAlignedWindow) and (
                stored.period_start <= now < stored.period_end
            ):
                return stored
            start, end = self._interval.period_around(self._anchor_at, moment)
            return CalendarAlignedWindow(self._id, self._limit, start.timestamp(), end.timestamp())
        if isinstance(stored, Window):
            return stored
        return Window(self._id, self._interval_seconds, self._limit, now)

    @staticmethod
    def _available(window: Window | CalendarAlignedWindow, now: float) -> int:
        if isinstance(window, Window):
            return window.available_tokens(now)
        return window.available_tokens()

    @staticmethod
    def _add(window: Window | CalendarAlignedWindow, tokens: int, now: float) -> None:
        if isinstance(window, Window):
            window.add(tokens, now)
        else:
            window.add(tokens)

    def _rate_limit(
        self,
        window: Window | CalendarAlignedWindow,
        now: float,
        *,
        retry_after: float,
        accepted: bool,
    ) -> RateLimit:
        # The window's end is fixed, so the reset does not drift as the clock moves inside it.
        reset_at = instant(window.availability_time(self._limit, now))
        return RateLimit(
            self._available(window, now),
            instant(retry_after),
            accepted=accepted,
            limit=self._limit,
            reset_at=reset_at,
            clock=self._clock,
        )
