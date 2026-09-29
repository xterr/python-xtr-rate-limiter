from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.support.limiters import window_factory
from xtr_rate_limiter import CompoundLimiter, InvalidArgumentError, ReserveNotSupportedError

if TYPE_CHECKING:
    from xtr_clock import MockClock

pytestmark = pytest.mark.anyio


async def test_the_tightest_accepting_limit_answers(clock: MockClock) -> None:
    compound = CompoundLimiter(
        [
            window_factory("wide", 10, clock).create("a"),
            window_factory("narrow", 3, clock).create("a"),
        ]
    )

    assert (await compound.consume()).remaining_tokens == 2


async def test_the_first_refusal_answers_and_earlier_limits_keep_their_spend(
    clock: MockClock,
) -> None:
    wide = window_factory("wide", 10, clock)
    compound = CompoundLimiter([wide.create("a"), window_factory("narrow", 1, clock).create("a")])
    _ = await compound.consume()

    refused = await compound.consume()

    assert not refused.is_accepted()
    assert (await wide.create("a").consume(0)).remaining_tokens == 8


async def test_it_cannot_reserve_and_resets_every_limit(clock: MockClock) -> None:
    limiter = CompoundLimiter([window_factory("only", 1, clock).create("a")])
    _ = await limiter.consume()

    with pytest.raises(ReserveNotSupportedError):
        _ = await limiter.reserve()
    await limiter.reset()

    assert (await limiter.consume()).is_accepted()


def test_it_refuses_nothing_to_combine() -> None:
    with pytest.raises(InvalidArgumentError):
        _ = CompoundLimiter([])
