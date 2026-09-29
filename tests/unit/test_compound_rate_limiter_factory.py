from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.support.limiters import window_factory
from xtr_rate_limiter import CompoundLimiter, CompoundRateLimiterFactory, InvalidArgumentError

if TYPE_CHECKING:
    from xtr_clock import MockClock

pytestmark = pytest.mark.anyio


async def test_it_combines_one_limiter_of_every_factory(clock: MockClock) -> None:
    compound = CompoundRateLimiterFactory(
        {"wide": window_factory("wide", 10, clock), "narrow": window_factory("narrow", 3, clock)}
    )

    limiter = compound.create("a")

    assert isinstance(limiter, CompoundLimiter)
    assert (await limiter.consume()).remaining_tokens == 2


async def test_a_key_can_be_shared_across_callers(clock: MockClock) -> None:
    compound = CompoundRateLimiterFactory(
        {"per_user": window_factory("user", 5, clock), "global": window_factory("all", 1, clock)},
        keys={"global": "everyone"},
    )
    _ = await compound.create("alice").consume()

    assert not (await compound.create("bob").consume()).is_accepted()


def test_it_refuses_nothing_to_combine_and_keys_for_strangers(clock: MockClock) -> None:
    with pytest.raises(InvalidArgumentError):
        _ = CompoundRateLimiterFactory({})
    with pytest.raises(InvalidArgumentError):
        _ = CompoundRateLimiterFactory({"a": window_factory("a", 1, clock)}, keys={"b": "x"})
