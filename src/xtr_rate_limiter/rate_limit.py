"""What a limiter answered: accepted or not, what is left, and when to come back."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from typing_extensions import override
from xtr_clock import Clock

from .exception import RateLimitExceededError

if TYPE_CHECKING:
    from datetime import datetime
    from typing import Self

    from xtr_clock import ClockInterface

__all__ = ["RateLimit"]


@final
class RateLimit:
    """The state of a limit, as one consumption left it.

    Two instants are told apart. :attr:`retry_after` is when the tokens this
    caller asked for become available; :attr:`reset_at` is when the limiter is
    back to holding every token — ``None`` for a limiter that has no such
    moment.

    ```python
    limit = await limiter.consume()
    if not limit.is_accepted():
        await limit.wait()
    ```
    """

    __slots__ = ("_accepted", "_clock", "_limit", "_remaining_tokens", "_reset_at", "_retry_after")

    def __init__(  # noqa: PLR0913 — the fields of the limit it describes; the clock by keyword.
        self,
        remaining_tokens: int,
        retry_after: datetime,
        accepted: bool,
        limit: int,
        reset_at: datetime | None = None,
        *,
        clock: ClockInterface | None = None,
    ) -> None:
        """Describe a limit.

        Args:
            remaining_tokens: How many tokens are left.
            retry_after: When the tokens asked for become available.
            accepted: Whether the consumption was accepted.
            limit: How many tokens the limiter holds when full.
            reset_at: When the limiter holds every token again, if it ever
                does.
            clock: What :meth:`wait` measures against; the clock in force
                when ``None``.
        """
        self._remaining_tokens = remaining_tokens
        self._retry_after = retry_after
        self._accepted = accepted
        self._limit = limit
        self._reset_at = reset_at
        self._clock: ClockInterface = clock if clock is not None else Clock()

    def is_accepted(self) -> bool:
        """Tell whether the tokens asked for were granted."""
        return self._accepted

    def ensure_accepted(self) -> Self:
        """Return this limit, or raise when it was not accepted.

        Raises:
            RateLimitExceededError: When the tokens were not granted.
        """
        if not self._accepted:
            raise RateLimitExceededError(self)
        return self

    @property
    def remaining_tokens(self) -> int:
        """How many tokens are left."""
        return self._remaining_tokens

    @property
    def retry_after(self) -> datetime:
        """When the tokens asked for become available."""
        return self._retry_after

    @property
    def limit(self) -> int:
        """How many tokens the limiter holds when full."""
        return self._limit

    @property
    def reset_at(self) -> datetime | None:
        """When the limiter holds every token again; ``None`` when it has no such moment."""
        return self._reset_at

    async def wait(self) -> None:
        """Wait until :attr:`retry_after`, without blocking the event loop."""
        delta = self._retry_after.timestamp() - self._clock.now().timestamp()
        await self._clock.sleep_async(delta)

    @override
    def __repr__(self) -> str:
        """Show the limit's state."""
        return (
            f"{type(self).__name__}(remaining_tokens={self._remaining_tokens!r}, "
            f"retry_after={self._retry_after.isoformat()!r}, accepted={self._accepted!r}, "
            f"limit={self._limit!r})"
        )
