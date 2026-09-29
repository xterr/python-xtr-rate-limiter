from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from xtr_rate_limiter import InvalidArgumentError, LimiterConfig, Rate


@pytest.mark.parametrize(
    "config",
    [
        LimiterConfig("fixed_window", limit=1, interval="1 minute"),
        LimiterConfig("fixed_window", limit=1, interval="1 month", anchor_at="2026-01-01"),
        LimiterConfig("sliding_window", limit=1, interval=timedelta(seconds=1)),
        LimiterConfig("token_bucket", limit=1, rate=Rate.per_minute()),
        LimiterConfig("no_limit"),
        LimiterConfig("compound", limiters=["a"], keys={"a": "all"}),
    ],
)
def test_it_accepts_every_policy_with_its_options(config: LimiterConfig) -> None:
    assert config.storage == "cache"


@pytest.mark.parametrize(
    "arguments",
    [
        {"policy": "leaky_bucket"},
        {"policy": "fixed_window", "interval": "1 minute"},
        {"policy": "fixed_window", "limit": 0, "interval": "1 minute"},
        {"policy": "fixed_window", "limit": 1},
        {"policy": "sliding_window", "limit": 1, "interval": "1 month", "anchor_at": "2026-01-01"},
        {"policy": "fixed_window", "limit": 1, "interval": "1 day", "anchor_at": "2026-01-01"},
        {"policy": "fixed_window", "limit": 1, "interval": "1 month", "anchor_at": "whenever"},
        {"policy": "token_bucket", "limit": 1},
        {"policy": "token_bucket", "limit": 1, "rate": Rate.per_second(), "interval": "1 second"},
        {
            "policy": "token_bucket",
            "limit": 1,
            "rate": Rate.per_second(),
            "anchor_at": "2026-01-01",
        },
        {"policy": "sliding_window", "limit": 1, "interval": "1 minute", "rate": Rate.per_second()},
        {"policy": "no_limit", "limit": 1},
        {"policy": "no_limit", "limiters": ["a"]},
        {"policy": "compound"},
        {"policy": "compound", "limiters": "a"},
        {"policy": "compound", "limiters": ["a"], "keys": {"b": "all"}},
        {"policy": "no_limit", "storage": ""},
        {"policy": "no_limit", "cache_pool": ""},
        {"policy": "no_limit", "lock": ""},
    ],
)
def test_it_refuses_options_missing_from_or_foreign_to_the_policy(
    arguments: dict[str, object],
) -> None:
    with pytest.raises(InvalidArgumentError):
        _ = LimiterConfig(**arguments)  # pyright: ignore[reportArgumentType]  # ty: ignore[invalid-argument-type]


def test_an_anchor_without_a_zone_is_read_as_utc() -> None:
    naive = LimiterConfig("fixed_window", limit=1, interval="1 month", anchor_at="2026-01-01")
    zoned = LimiterConfig(
        "fixed_window",
        limit=1,
        interval="1 month",
        anchor_at=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2))),
    )

    assert naive.anchor() == datetime(2026, 1, 1, tzinfo=UTC)
    assert zoned.anchor() == datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2)))
    assert LimiterConfig("no_limit").anchor() is None


def test_only_a_window_has_an_interval() -> None:
    with pytest.raises(InvalidArgumentError):
        _ = LimiterConfig("no_limit").parsed_interval()
