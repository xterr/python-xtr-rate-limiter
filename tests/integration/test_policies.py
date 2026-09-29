"""Every policy answers the same whether it counts in memory, in a cache pool or in Redis."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from tests.support.backends import BACKENDS, make_factory
from xtr_rate_limiter import (
    InvalidArgumentError,
    LimiterConfig,
    MaxWaitDurationExceededError,
    Rate,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from fakeredis import FakeAsyncRedis
    from xtr_clock import MockClock

    from xtr_rate_limiter import RateLimiterFactoryInterface

pytestmark = pytest.mark.anyio


@pytest.fixture(params=BACKENDS)
def factory_for(
    request: pytest.FixtureRequest, clock: MockClock, redis_client: FakeAsyncRedis
) -> Callable[[LimiterConfig], RateLimiterFactoryInterface]:
    backend = cast("str", request.param)
    return make_factory(backend, clock, redis_client)


def _now(clock: MockClock) -> float:
    return clock.now().timestamp()


# ── fixed window ──────────────────────────────────────────────────────────


async def test_a_fixed_window_accepts_up_to_its_limit_then_refuses(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface], clock: MockClock
) -> None:
    limiter = factory_for(LimiterConfig("fixed_window", limit=3, interval="1 minute")).create("a")
    start = _now(clock)

    remaining = [(await limiter.consume()).remaining_tokens for _ in range(3)]
    refused = await limiter.consume()

    assert remaining == [2, 1, 0]
    assert not refused.is_accepted()
    assert refused.remaining_tokens == 0
    assert refused.retry_after.timestamp() == pytest.approx(start + 60)
    assert refused.reset_at is not None
    assert refused.reset_at.timestamp() == pytest.approx(start + 60)


async def test_the_last_token_of_a_fixed_window_says_when_the_next_one_is_free(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface], clock: MockClock
) -> None:
    limiter = factory_for(LimiterConfig("fixed_window", limit=2, interval="1 minute")).create("a")
    start = _now(clock)

    first = await limiter.consume()
    last = await limiter.consume()

    assert first.retry_after.timestamp() == pytest.approx(start)
    assert last.is_accepted()
    assert last.retry_after.timestamp() == pytest.approx(start + 60)


async def test_a_fixed_window_accepts_again_once_it_ends(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface], clock: MockClock
) -> None:
    limiter = factory_for(LimiterConfig("fixed_window", limit=1, interval="1 minute")).create("a")
    _ = await limiter.consume()

    clock.sleep(61)

    assert (await limiter.consume()).is_accepted()


async def test_keys_are_counted_apart(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface],
) -> None:
    factory = factory_for(LimiterConfig("fixed_window", limit=1, interval="1 minute"))
    _ = await factory.create("a").consume()

    assert (await factory.create("b").consume()).is_accepted()
    assert not (await factory.create("a").consume()).is_accepted()


async def test_a_reservation_waits_for_the_next_window_and_its_debt_is_carried(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface], clock: MockClock
) -> None:
    limiter = factory_for(LimiterConfig("fixed_window", limit=1, interval="1 minute")).create("a")
    start = _now(clock)
    _ = await limiter.consume()

    second = await limiter.reserve()
    third = await limiter.reserve()

    assert second.time_to_act == pytest.approx(start + 60)
    assert third.time_to_act == pytest.approx(start + 120)
    assert not second.rate_limit.is_accepted()

    clock.sleep(61)
    assert not (await limiter.consume()).is_accepted()


async def test_a_reservation_longer_than_the_caller_waits_books_nothing(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface], clock: MockClock
) -> None:
    limiter = factory_for(LimiterConfig("fixed_window", limit=1, interval="1 minute")).create("a")
    _ = await limiter.consume()

    with pytest.raises(MaxWaitDurationExceededError) as raised:
        _ = await limiter.reserve(max_time=10)

    assert raised.value.wait_duration == pytest.approx(60)
    assert raised.value.max_time == 10
    assert not raised.value.rate_limit.is_accepted()
    clock.sleep(61)
    assert (await limiter.consume()).is_accepted()


async def test_consuming_nothing_reports_the_limit_and_spends_nothing(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface],
) -> None:
    limiter = factory_for(LimiterConfig("fixed_window", limit=2, interval="1 minute")).create("a")

    peek = await limiter.consume(0)

    assert peek.is_accepted()
    assert peek.remaining_tokens == 2
    assert (await limiter.consume(2)).is_accepted()


async def test_a_reset_forgets_every_hit(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface],
) -> None:
    limiter = factory_for(LimiterConfig("fixed_window", limit=1, interval="1 minute")).create("a")
    _ = await limiter.consume()

    await limiter.reset()

    assert (await limiter.consume()).is_accepted()


@pytest.mark.parametrize("tokens", [-1, 3])
async def test_a_limiter_refuses_tokens_it_could_never_hold(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface], tokens: int
) -> None:
    limiter = factory_for(LimiterConfig("fixed_window", limit=2, interval="1 minute")).create("a")

    with pytest.raises(InvalidArgumentError):
        _ = await limiter.consume(tokens)


# ── fixed window on a calendar ────────────────────────────────────────────


async def test_a_calendar_window_ends_at_the_next_period_whenever_the_first_hit_came(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface], clock: MockClock
) -> None:
    config = LimiterConfig(
        "fixed_window", limit=2, interval="1 month", anchor_at="2026-01-01T00:00:00"
    )
    limiter = factory_for(config).create("a")
    february = datetime(2026, 2, 1, tzinfo=UTC).timestamp()

    _ = await limiter.consume(2)
    refused = await limiter.consume()

    assert not refused.is_accepted()
    assert refused.retry_after.timestamp() == pytest.approx(february)
    assert refused.reset_at is not None
    assert refused.reset_at.timestamp() == pytest.approx(february)

    clock.modify("2026-02-01 00:00:01")
    assert (await limiter.consume(2)).is_accepted()


async def test_a_calendar_window_reserves_into_the_next_period(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface],
) -> None:
    config = LimiterConfig(
        "fixed_window", limit=1, interval="1 month", anchor_at="2026-01-01T00:00:00+00:00"
    )
    limiter = factory_for(config).create("a")
    _ = await limiter.consume()

    reservation = await limiter.reserve()

    assert reservation.time_to_act == pytest.approx(datetime(2026, 2, 1, tzinfo=UTC).timestamp())
    with pytest.raises(MaxWaitDurationExceededError):
        _ = await limiter.reserve(max_time=60)


# ── sliding window ────────────────────────────────────────────────────────


async def test_a_sliding_window_still_counts_part_of_the_last_window(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface], clock: MockClock
) -> None:
    limiter = factory_for(LimiterConfig("sliding_window", limit=4, interval="1 minute")).create("a")
    _ = await limiter.consume(4)
    assert not (await limiter.consume()).is_accepted()

    clock.sleep(90)

    # Half of the last window's four hits still lie within the last minute.
    assert (await limiter.consume(2)).is_accepted()
    assert not (await limiter.consume()).is_accepted()


async def test_a_sliding_window_forgets_a_window_idle_for_longer_than_itself(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface], clock: MockClock
) -> None:
    limiter = factory_for(LimiterConfig("sliding_window", limit=2, interval="1 minute")).create("a")
    _ = await limiter.consume(2)

    clock.sleep(200)

    assert (await limiter.consume(2)).is_accepted()


async def test_a_sliding_window_peek_and_reservation(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface], clock: MockClock
) -> None:
    limiter = factory_for(LimiterConfig("sliding_window", limit=2, interval="1 minute")).create("a")
    start = _now(clock)

    fresh = await limiter.consume(0)
    exhausted = await limiter.consume(2)
    peek = await limiter.consume(0)
    reservation = await limiter.reserve()

    assert fresh.remaining_tokens == 2
    assert fresh.reset_at is not None
    assert fresh.reset_at.timestamp() == pytest.approx(start)
    assert exhausted.retry_after.timestamp() > start
    assert peek.remaining_tokens == 0
    assert peek.retry_after.timestamp() > start
    assert reservation.time_to_act > start
    with pytest.raises(MaxWaitDurationExceededError):
        _ = await limiter.reserve(max_time=0.001)


# ── token bucket ──────────────────────────────────────────────────────────


async def test_a_token_bucket_bursts_then_refills_at_its_rate(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface], clock: MockClock
) -> None:
    config = LimiterConfig("token_bucket", limit=2, rate=Rate("10 seconds"))
    limiter = factory_for(config).create("a")
    start = _now(clock)

    burst = [(await limiter.consume()).is_accepted() for _ in range(2)]
    refused = await limiter.consume()

    assert burst == [True, True]
    assert not refused.is_accepted()
    assert refused.retry_after.timestamp() == pytest.approx(start + 10)
    assert refused.reset_at is not None
    assert refused.reset_at.timestamp() == pytest.approx(start + 20)

    clock.sleep(10)
    assert (await limiter.consume()).is_accepted()
    assert not (await limiter.consume()).is_accepted()


async def test_a_token_bucket_reserves_in_line(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface], clock: MockClock
) -> None:
    config = LimiterConfig("token_bucket", limit=1, rate=Rate("10 seconds", amount=1))
    limiter = factory_for(config).create("a")
    start = _now(clock)
    _ = await limiter.consume()

    second = await limiter.reserve()
    third = await limiter.reserve()

    assert second.time_to_act == pytest.approx(start + 10)
    assert third.time_to_act == pytest.approx(start + 20)
    assert second.rate_limit.remaining_tokens == 0
    with pytest.raises(MaxWaitDurationExceededError):
        _ = await limiter.reserve(max_time=5)


async def test_a_token_bucket_never_holds_more_than_its_burst(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface], clock: MockClock
) -> None:
    config = LimiterConfig("token_bucket", limit=2, rate=Rate.per_second(5))
    limiter = factory_for(config).create("a")
    _ = await limiter.consume(2)

    clock.sleep(60)

    assert (await limiter.consume(0)).remaining_tokens == 2


# ── no limit ──────────────────────────────────────────────────────────────


async def test_no_limit_accepts_everything(
    factory_for: Callable[[LimiterConfig], RateLimiterFactoryInterface],
) -> None:
    limiter = factory_for(LimiterConfig("no_limit")).create("a")

    limits = [await limiter.consume(1_000) for _ in range(3)]

    assert all(limit.is_accepted() for limit in limits)
    assert (await limiter.reserve()).wait_duration() == 0
    await limiter.reset()
