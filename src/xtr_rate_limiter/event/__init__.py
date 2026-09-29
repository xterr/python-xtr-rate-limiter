"""The events a caller of a limiter dispatches."""

from __future__ import annotations

from .rate_limit_exceeded_event import RateLimitExceededEvent

__all__ = ["RateLimitExceededEvent"]
