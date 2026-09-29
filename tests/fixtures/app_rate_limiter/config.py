"""One limiter per kind of storage and policy the bundle can build."""

from __future__ import annotations

from redis.asyncio import Redis
from xtr_cache.bundle import CacheConfig
from xtr_dependency_injection import Reference, configure, env
from xtr_lock.bundle import LockConfig

from xtr_rate_limiter import LimiterConfig, Rate, StorageInterface
from xtr_rate_limiter.bundle import BuilderConfig, RateLimiterConfig

from .services import LIMITS


@configure
def cache() -> CacheConfig:
    return CacheConfig(app="array", stampede_lock=None)


@configure
def lock() -> LockConfig:
    return LockConfig(resources={"default": "in-memory", "limits": "in-memory"})


@configure
def rate_limiter() -> RateLimiterConfig:
    return RateLimiterConfig(
        limiters={
            "api": LimiterConfig("sliding_window", limit=2, interval="1 minute"),
            "login": LimiterConfig(
                "fixed_window", limit=1, interval="15 minutes", storage=env("RL_LOGIN_STORAGE")
            ),
            "uploads": LimiterConfig(
                "token_bucket",
                limit=1,
                rate=Rate.per_minute(),
                storage="in-memory",
                lock="limits",
            ),
            "local": LimiterConfig(
                "fixed_window", limit=1, interval="1 minute", storage="in-memory", lock=None
            ),
            "atomic": LimiterConfig(
                "fixed_window", limit=1, interval="1 minute", storage=Reference(Redis, LIMITS)
            ),
            "custom": LimiterConfig(
                "fixed_window",
                limit=1,
                interval="1 minute",
                storage=Reference(StorageInterface, LIMITS),
            ),
            "dsn": LimiterConfig(
                "fixed_window", limit=1, interval="1 minute", storage=env("RL_REDIS_DSN")
            ),
            "open": LimiterConfig("no_limit"),
            "strict": LimiterConfig("compound", limiters=["api", "local"]),
        },
        builder=BuilderConfig(storage=env("RL_BUILDER_STORAGE")),
    )
