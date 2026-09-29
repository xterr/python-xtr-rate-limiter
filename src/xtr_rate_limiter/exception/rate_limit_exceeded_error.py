"""A hit the caller insisted on was not accepted."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .rate_limiter_error import RateLimiterError

if TYPE_CHECKING:
    from datetime import datetime

    from xtr_rate_limiter.rate_limit import RateLimit

__all__ = ["RateLimitExceededError"]


class RateLimitExceededError(RateLimiterError):
    """A hit the caller insisted on was not accepted.

    Raised by :meth:`RateLimit.ensure_accepted
    <xtr_rate_limiter.rate_limit.RateLimit.ensure_accepted>`, for code that
    would rather fail than branch on the answer.

    Attributes:
        rate_limit: The rejected limit.
    """

    rate_limit: RateLimit

    def __init__(self, rate_limit: RateLimit) -> None:
        """Record the rejected limit."""
        self.rate_limit = rate_limit
        super().__init__(
            f"Rate limit exceeded: {rate_limit.remaining_tokens} of {rate_limit.limit} "
            f"tokens left, retry after {rate_limit.retry_after.isoformat()}.",
        )

    @property
    def retry_after(self) -> datetime:
        """When the tokens asked for become available."""
        return self.rate_limit.retry_after

    @property
    def remaining_tokens(self) -> int:
        """How many tokens are left."""
        return self.rate_limit.remaining_tokens

    @property
    def limit(self) -> int:
        """How many tokens the limiter holds when full."""
        return self.rate_limit.limit
