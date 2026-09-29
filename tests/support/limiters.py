"""Small limiters for the tests that combine them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from xtr_rate_limiter import InMemoryStorage, LimiterConfig, RateLimiterFactory

if TYPE_CHECKING:
    from xtr_clock import MockClock

__all__ = ["window_factory"]


def window_factory(name: str, limit: int, clock: MockClock) -> RateLimiterFactory:
    """Return ``limit`` hits a minute, kept in memory, named ``name``."""
    config = LimiterConfig("fixed_window", limit=limit, interval="1 minute")
    return RateLimiterFactory(name, config, InMemoryStorage(clock), clock=clock)
