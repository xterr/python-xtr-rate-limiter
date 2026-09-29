"""The state of a fixed window aligned to a calendar."""

from __future__ import annotations

from typing import final

__all__ = ["CalendarAlignedWindow"]


@final
class CalendarAlignedWindow:
    """Hits counted in one period of a calendar, from its start to its end.

    The period is fixed — the first of the month to the first of the next,
    say — whatever moment the first hit arrived, and every hit it counted is
    forgotten when it ends.
    """

    __slots__ = ("_hit_count", "_id", "_max_size", "_period_end", "_period_start")

    def __init__(
        self, state_id: str, max_size: int, period_start: float, period_end: float
    ) -> None:
        """Count up to ``max_size`` hits between ``period_start`` and ``period_end``."""
        self._id = state_id
        self._max_size = max_size
        self._period_start = period_start
        self._period_end = period_end
        self._hit_count = 0

    @property
    def id(self) -> str:
        """The limiter's id and key."""
        return self._id

    @property
    def expires_at(self) -> float:
        """The end of the period: nothing counted in it matters afterwards."""
        return self._period_end

    @property
    def period_start(self) -> float:
        """When the period started, in seconds since the epoch."""
        return self._period_start

    @property
    def period_end(self) -> float:
        """When the period ends, in seconds since the epoch."""
        return self._period_end

    @property
    def hit_count(self) -> int:
        """The hits counted in the period."""
        return self._hit_count

    def add(self, hits: int) -> None:
        """Count ``hits``."""
        self._hit_count = max(0, self._hit_count + hits)

    def available_tokens(self) -> int:
        """Return how many hits the period still takes; negative while in debt."""
        return self._max_size - self._hit_count

    def time_for_tokens(self, tokens: int, now: float) -> float:
        """Return how many seconds from ``now`` until ``tokens`` hits are taken."""
        return max(0.0, self.availability_time(tokens, now) - now)

    def availability_time(self, tokens: int, now: float) -> float:
        """Return the instant ``tokens`` hits are taken: now, or when the period ends."""
        if self._max_size - self._hit_count >= tokens:
            return now
        return self._period_end
