from __future__ import annotations

import asyncio

import pytest
from xtr_lock import InMemoryStore, LockFactory

from tests.support.yielding_storage import YieldingStorage
from xtr_rate_limiter import InvalidArgumentError, LimiterConfig, RateLimiterFactory
from xtr_rate_limiter.policy._stored_limiter import check_limit, check_tokens

_CONCURRENT = 20
"""How many reservations arrive at once in the concurrency test."""

_LIMIT = 3
"""How many of them the limiter may accept."""


@pytest.mark.anyio
async def test_a_shared_limiter_admits_no_more_than_its_limit_under_concurrency() -> None:
    factory = RateLimiterFactory(
        "shared",
        LimiterConfig("fixed_window", limit=_LIMIT, interval="1 minute"),
        YieldingStorage(),
        LockFactory(InMemoryStore()),
    )
    limiter = factory.create("k")

    answers = await asyncio.gather(*(limiter.consume() for _ in range(_CONCURRENT)))

    assert sum(answer.is_accepted() for answer in answers) == _LIMIT


@pytest.mark.parametrize(("tokens", "match"), [(-1, "negative"), (3, "more tokens")])
def test_it_refuses_tokens_it_could_never_hold(tokens: int, match: str) -> None:
    with pytest.raises(InvalidArgumentError, match=match):
        check_tokens(tokens, 2, "size")


def test_it_refuses_a_limit_that_would_accept_nothing() -> None:
    check_limit(1)
    with pytest.raises(InvalidArgumentError):
        check_limit(0)
