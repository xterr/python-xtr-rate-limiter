from __future__ import annotations

import pytest

from xtr_rate_limiter import InvalidArgumentError, LimiterConfig
from xtr_rate_limiter.bundle import BuilderConfig, RateLimiterConfig

_WINDOW = LimiterConfig("fixed_window", limit=1, interval="1 minute")


def test_it_builds_with_no_arguments() -> None:
    config = RateLimiterConfig()

    assert config.limiters == {}
    assert config.builder == BuilderConfig()
    assert config.redis_prefix == "rate_limiter:"


@pytest.mark.parametrize(
    "limiters",
    [
        {"": _WINDOW},
        {"api": "fixed_window"},
        {"api": LimiterConfig("fixed_window", limit=1, interval="1 minute", storage=3)},  # pyright: ignore[reportArgumentType]  # ty: ignore[invalid-argument-type]
        {"strict": LimiterConfig("compound", limiters=["missing"])},
        {
            "api": _WINDOW,
            "inner": LimiterConfig("compound", limiters=["api"]),
            "outer": LimiterConfig("compound", limiters=["inner"]),
        },
    ],
)
def test_it_refuses_a_limiter_it_cannot_register(limiters: dict[str, object]) -> None:
    with pytest.raises(InvalidArgumentError):
        _ = RateLimiterConfig(limiters=limiters)  # pyright: ignore[reportArgumentType]  # ty: ignore[invalid-argument-type]
