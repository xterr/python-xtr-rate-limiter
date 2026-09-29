"""The state of a token bucket: the tokens in it, and when it was last topped up."""

from __future__ import annotations

import math
from typing import final

from xtr_rate_limiter.exception import InvalidArgumentError

__all__ = ["TokenBucket"]


@final
class TokenBucket:
    """A bucket of tokens, topped up by a fixed amount every cycle.

    Reservations beyond what the bucket holds leave it in debt — a negative
    count — which later refills pay back before anyone else is served.
    """

    __slots__ = ("_amount", "_burst_size", "_cycle", "_expires_at", "_id", "_timer", "_tokens")

    def __init__(
        self,
        state_id: str,
        initial_tokens: int,
        cycle: float,
        amount: int,
        timer: float,
    ) -> None:
        """Fill a bucket of ``initial_tokens``, topped up by ``amount`` every ``cycle`` seconds.

        Raises:
            InvalidArgumentError: When ``initial_tokens`` is below one.
        """
        if initial_tokens < 1:
            raise InvalidArgumentError(
                f"Cannot set the limit to {initial_tokens}, as that would never accept any hit.",
            )
        self._id = state_id
        self._tokens = initial_tokens
        self._burst_size = initial_tokens
        self._cycle = cycle
        self._amount = amount
        self._timer = timer
        self._expires_at = timer + self.time_for_tokens(initial_tokens)

    @property
    def id(self) -> str:
        """The limiter's id and key."""
        return self._id

    @property
    def expires_at(self) -> float:
        """Long enough to refill completely, and to pay back any debt."""
        return self._expires_at

    @property
    def timer(self) -> float:
        """When the bucket was last topped up, in seconds since the epoch."""
        return self._timer

    def set_tokens(self, tokens: int, now: float) -> None:
        """Leave ``tokens`` in the bucket at ``now``; negative for a debt.

        ``tokens`` counts every refill up to ``now``, so the timer moves up to
        the last whole cycle before it — only whole cycles move it, so a
        partial one is never lost.
        """
        self._timer += self._cycles(now) * self._cycle
        self._tokens = tokens
        owed = max(self._burst_size, self._burst_size - tokens)
        self._expires_at = now + self.time_for_tokens(owed)

    def available_tokens(self, now: float) -> int:
        """Return the tokens in the bucket at ``now``, counting every whole cycle's refill."""
        return min(self._burst_size, self._tokens + self._cycles(now) * self._amount)

    def _cycles(self, now: float) -> int:
        return math.floor(max(0.0, now - self._timer) / self._cycle)

    def time_for_tokens(self, tokens: int) -> float:
        """Return how many seconds refilling ``tokens`` takes."""
        return math.ceil(tokens / self._amount) * self._cycle
