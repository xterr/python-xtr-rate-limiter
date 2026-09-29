"""Every error this library raises.

All of them derive from :class:`RateLimiterError`, so one ``except`` catches
anything a limiter can go wrong with, and a narrower one handles a single
cause. Each carries the data a caller needs as typed attributes rather than
forcing a message to be parsed.
"""

from __future__ import annotations

from .invalid_argument_error import InvalidArgumentError
from .invalid_interval_error import InvalidIntervalError
from .max_wait_duration_exceeded_error import MaxWaitDurationExceededError
from .rate_limit_exceeded_error import RateLimitExceededError
from .rate_limiter_error import RateLimiterError
from .rate_limiter_storage_error import RateLimiterStorageError
from .reserve_not_supported_error import ReserveNotSupportedError

__all__ = [
    "InvalidArgumentError",
    "InvalidIntervalError",
    "MaxWaitDurationExceededError",
    "RateLimitExceededError",
    "RateLimiterError",
    "RateLimiterStorageError",
    "ReserveNotSupportedError",
]
