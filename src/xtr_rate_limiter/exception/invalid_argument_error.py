"""A limiter, a factory or a storage was given an argument it cannot work with."""

from __future__ import annotations

from .rate_limiter_error import RateLimiterError

__all__ = ["InvalidArgumentError"]


class InvalidArgumentError(RateLimiterError, ValueError):
    """A limiter, a factory or a storage was given an argument it cannot work with.

    Raised where the argument is given — a limit below one, more tokens than
    a limiter can ever hold, a policy option that belongs to another policy —
    rather than on the first hit.

    Also a :class:`ValueError`, so code that already guards its configuration
    with ``except ValueError`` keeps working without learning a new exception.

    Attributes:
        reason: What is wrong with the argument.
    """

    reason: str

    def __init__(self, reason: str) -> None:
        """Record what is wrong with the argument."""
        self.reason = reason
        super().__init__(reason)
