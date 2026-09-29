"""Limits on how often anything may happen: calls, jobs, logins, messages.

A :class:`~xtr_rate_limiter.rate_limiter_factory_interface.RateLimiterFactoryInterface`
is one configured limit; it hands out a
:class:`~xtr_rate_limiter.limiter_interface.LimiterInterface` per key — a
user, an address, an account — which answers whether a hit may go ahead:

```python
factory = RateLimiterFactory(
    "api",
    LimiterConfig("sliding_window", limit=100, interval="1 minute"),
    InMemoryStorage(),
)

limit = await factory.create(client_ip).consume()
if not limit.is_accepted():
    ...  # refuse, or `await limit.wait()`
```

Three policies count hits — a fixed window, a sliding window, a token
bucket — and a fourth counts nothing. State lives in a
:class:`~xtr_rate_limiter.storage.StorageInterface` under a lock, or on a
Redis server that counts each hit atomically
(:class:`~xtr_rate_limiter.redis.RedisRateLimiterFactory`).

Every call that touches a limiter is awaited.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .compound_limiter import CompoundLimiter
from .compound_rate_limiter_factory import CompoundRateLimiterFactory
from .event import RateLimitExceededEvent
from .exception import (
    InvalidArgumentError,
    InvalidIntervalError,
    MaxWaitDurationExceededError,
    RateLimiterError,
    RateLimiterStorageError,
    RateLimitExceededError,
    ReserveNotSupportedError,
)
from .limiter_config import LimiterConfig, Policy
from .limiter_interface import LimiterInterface
from .limiter_state_interface import LimiterStateInterface
from .policy import (
    FixedWindowLimiter,
    NoLimiter,
    Rate,
    SlidingWindowLimiter,
    TokenBucketLimiter,
)
from .rate_limit import RateLimit
from .rate_limiter_builder import RateLimiterBuilder
from .rate_limiter_factory import RateLimiterFactory
from .rate_limiter_factory_interface import RateLimiterFactoryInterface
from .reservation import Reservation
from .storage import CacheStorage, InMemoryStorage, StorageInterface

try:
    __version__ = version("xtr-rate-limiter")
except PackageNotFoundError:  # pragma: no cover
    # Running from a source tree or a vendored copy, with no installed
    # metadata to read. Having no version is better than refusing to import.
    __version__ = "0+unknown"

__all__ = [
    "CacheStorage",
    "CompoundLimiter",
    "CompoundRateLimiterFactory",
    "FixedWindowLimiter",
    "InMemoryStorage",
    "InvalidArgumentError",
    "InvalidIntervalError",
    "LimiterConfig",
    "LimiterInterface",
    "LimiterStateInterface",
    "MaxWaitDurationExceededError",
    "NoLimiter",
    "Policy",
    "Rate",
    "RateLimit",
    "RateLimitExceededError",
    "RateLimitExceededEvent",
    "RateLimiterBuilder",
    "RateLimiterError",
    "RateLimiterFactory",
    "RateLimiterFactoryInterface",
    "RateLimiterStorageError",
    "Reservation",
    "ReserveNotSupportedError",
    "SlidingWindowLimiter",
    "StorageInterface",
    "TokenBucketLimiter",
    "__version__",
]
