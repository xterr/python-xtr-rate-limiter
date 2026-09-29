"""The state of a fixed window that opens on its first hit."""

from __future__ import annotations

import math
from typing import final

__all__ = ["Window"]


@final
class Window:
    """Hits counted in a window of fixed length that starts on the first hit.

    Tokens reserved beyond the window's size are a debt the next windows pay:
    when a window rolls over, the hits it could not hold are carried into the
    one after, so a reservation never hands out tokens twice.
    """

    __slots__ = ("_expires_at", "_hit_count", "_id", "_interval", "_max_size", "_timer")

    def __init__(self, state_id: str, interval: float, window_size: int, timer: float) -> None:
        """Open a window of ``interval`` seconds for ``window_size`` hits at ``timer``."""
        self._id = state_id
        self._interval = interval
        self._max_size = window_size
        self._timer = timer
        self._hit_count = 0
        self._expires_at = timer + interval

    @property
    def id(self) -> str:
        """The limiter's id and key."""
        return self._id

    @property
    def expires_at(self) -> float:
        """Long enough for any debt to be carried forward, however far it reaches."""
        return self._expires_at

    @property
    def hit_count(self) -> int:
        """The hits counted, debt included, as of the window's start."""
        return self._hit_count

    def add(self, hits: int, now: float) -> None:
        """Count ``hits`` at ``now``, rolling the window over first when it has ended."""
        if now - self._timer > self._interval:
            self._hit_count = self._carried_hit_count(now)
            self._timer = now
        self._hit_count = max(0, self._hit_count + hits)
        windows = max(1, math.ceil(self._hit_count / self._max_size))
        self._expires_at = now + self._interval * windows

    def available_tokens(self, now: float) -> int:
        """Return how many hits the window still takes at ``now``; negative while in debt."""
        return self._max_size - self._carried_hit_count(now)

    def time_for_tokens(self, tokens: int, now: float) -> float:
        """Return how many seconds from ``now`` until ``tokens`` hits are taken."""
        return max(0.0, self.availability_time(tokens, now) - now)

    def availability_time(self, tokens: int, now: float) -> float:
        """Return the instant ``tokens`` hits are taken, which does not move with the clock."""
        if self._max_size - self._hit_count >= tokens:
            return now
        in_window = math.ceil((self._hit_count + tokens) / self._max_size) - 1
        return self._timer + self._interval * in_window

    def _carried_hit_count(self, now: float) -> int:
        """Return the hits still owed at ``now``, after every window that has since ended."""
        elapsed = now - self._timer
        if elapsed <= self._interval:
            return self._hit_count
        windows_elapsed = int(elapsed / self._interval)
        return max(0, self._hit_count - windows_elapsed * self._max_size)
