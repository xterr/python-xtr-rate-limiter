"""A limiter and a builder both pointed at a service that is no storage."""

from __future__ import annotations

from xtr_dependency_injection import Reference, configure

from xtr_rate_limiter import LimiterConfig
from xtr_rate_limiter.bundle import BuilderConfig, RateLimiterConfig

from .services import ODD, OddService


@configure
def rate_limiter() -> RateLimiterConfig:
    return RateLimiterConfig(
        limiters={
            "wrong": LimiterConfig(
                "fixed_window",
                limit=1,
                interval="1 minute",
                storage=Reference(OddService, ODD),
                lock=None,
            ),
        },
        builder=BuilderConfig(storage=Reference(OddService, ODD), lock=None),
    )
