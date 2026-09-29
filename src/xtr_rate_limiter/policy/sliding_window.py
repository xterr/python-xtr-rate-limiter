"""The state of a sliding window: this window's hits and a fading share of the last one's."""

from __future__ import annotations

import math
from typing import Self, final

from xtr_rate_limiter.exception import InvalidIntervalError

__all__ = ["SlidingWindow"]


@final
class SlidingWindow:
    """Hits counted over a window that slides, estimated from two fixed ones.

    Say the last window took 8 hits, the current one has taken 3, and a
    quarter of the current window has passed. Three quarters of the last
    window still lie inside the sliding one, so it holds 0.75 * 8 + 3 = 9
    hits. Two counters give that estimate without remembering every hit.
    """

    __slots__ = ("_hit_count", "_hit_count_for_last_window", "_id", "_interval", "_window_end_at")

    def __init__(self, state_id: str, interval: float, now: float) -> None:
        """Open a window of ``interval`` seconds at ``now``.

        Raises:
            InvalidIntervalError: When ``interval`` is not positive.
        """
        if interval <= 0:
            raise InvalidIntervalError(interval, "the interval must be positive")
        self._id = state_id
        self._interval = interval
        self._hit_count = 0
        self._hit_count_for_last_window = 0
        self._window_end_at = now + interval

    @classmethod
    def from_previous_window(cls, window: SlidingWindow, interval: float, now: float) -> Self:
        """Open the window after ``window``, carrying its hits when it ended just now.

        A limiter idle for more than a whole window carries nothing: the last
        window's hits have all slid out.
        """
        new = cls(window.id, interval, now)
        window_end_at = window._window_end_at + interval
        if now < window_end_at:
            new._hit_count_for_last_window = window._hit_count
            new._window_end_at = window_end_at
        return new

    @property
    def id(self) -> str:
        """The limiter's id and key."""
        return self._id

    @property
    def expires_at(self) -> float:
        """The end of the window after this one, once this one's hits have slid out."""
        return self._window_end_at + self._interval

    def is_expired(self, now: float) -> bool:
        """Tell whether the window has ended at ``now``."""
        return now > self._window_end_at

    def add(self, hits: int) -> None:
        """Count ``hits`` in this window."""
        self._hit_count = max(0, self._hit_count + hits)

    def hit_count(self, now: float) -> int:
        """Return the hits the sliding window holds at ``now``."""
        start_of_window = self._window_end_at - self._interval
        percent = min((now - start_of_window) / self._interval, 1)
        return math.floor(self._hit_count_for_last_window * (1 - percent) + self._hit_count)

    def full_capacity_time(self, now: float) -> float:
        """Return when the window holds no hits at all."""
        # Hits only start sliding out once carried into the next window.
        if self._hit_count:
            return self._window_end_at + self._interval * (1 - 1 / self._hit_count)
        if self._hit_count_for_last_window:
            return self._window_end_at - self._interval / self._hit_count_for_last_window
        return now

    def time_for_tokens(self, max_size: int, tokens: int, now: float) -> float:
        """Return how many seconds from ``now`` until ``tokens`` more hits fit in ``max_size``."""
        remaining = max_size - self.hit_count(now)
        if remaining >= tokens:
            return 0.0
        start_of_window = self._window_end_at - self._interval
        time_passed = now - start_of_window
        window_passed = min(time_passed / self._interval, 1)
        releasable = max(
            1, max_size - math.floor(self._hit_count_for_last_window * (1 - window_passed))
        )
        remaining_window = self._interval - time_passed
        needed = tokens - remaining
        if releasable >= needed:
            return needed * (remaining_window / max(1, releasable))
        return (self._window_end_at - now) + (needed - releasable) * (self._interval / max_size)
