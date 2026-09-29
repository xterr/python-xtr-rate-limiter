"""The server keeping a limiter's state failed to answer."""

from __future__ import annotations

from .rate_limiter_error import RateLimiterError

__all__ = ["RateLimiterStorageError"]


class RateLimiterStorageError(RateLimiterError):
    """The server keeping a limiter's state failed to answer.

    Raised rather than answering as if the limiter were empty: whether a
    limit fails open or closed is the caller's decision, not the storage's.

    Attributes:
        reason: What the server said, or why it could not be reached.
    """

    reason: str

    def __init__(self, reason: str) -> None:
        """Record why the state could not be read or written."""
        self.reason = reason
        super().__init__(reason)
