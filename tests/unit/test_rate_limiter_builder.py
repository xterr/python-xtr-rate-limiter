from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from xtr_rate_limiter import InMemoryStorage, NoLimiter, RateLimiterBuilder

if TYPE_CHECKING:
    from xtr_clock import MockClock

pytestmark = pytest.mark.anyio


async def test_the_builder_builds_every_policy(clock: MockClock) -> None:
    builder = RateLimiterBuilder(InMemoryStorage(clock), clock=clock)

    sliding = builder.sliding_window("s", 1, "1 minute")
    fixed = builder.fixed_window("f", 1, "1 month", anchor_at="2026-01-01")
    bucket = builder.token_bucket("t", 1, "1 second", amount=2)
    compound = builder.compound(sliding, bucket)

    assert (await fixed.create("a").consume()).is_accepted()
    assert (await compound.create("a").consume()).is_accepted()
    assert not (await compound.create("a").consume()).is_accepted()
    assert isinstance(builder.noop().create(), NoLimiter)
