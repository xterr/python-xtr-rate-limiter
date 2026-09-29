from __future__ import annotations

import pytest

from xtr_rate_limiter import InvalidArgumentError
from xtr_rate_limiter.policy.token_bucket import TokenBucket


def test_it_refills_by_whole_cycles_and_never_loses_a_partial_one() -> None:
    bucket = TokenBucket("t", 4, cycle=10, amount=1, timer=0)
    bucket.set_tokens(0, now=0)

    assert bucket.available_tokens(15) == 1
    assert bucket.available_tokens(20) == 2

    bucket.set_tokens(1, now=25)

    assert bucket.timer == 20
    assert bucket.available_tokens(29) == 1
    assert bucket.available_tokens(30) == 2


def test_it_holds_at_most_its_burst_and_remembers_a_debt() -> None:
    bucket = TokenBucket("t", 2, cycle=10, amount=5, timer=0)
    assert bucket.available_tokens(100) == 2

    bucket.set_tokens(-3, now=100)

    assert bucket.expires_at == 100 + bucket.time_for_tokens(5)
    assert bucket.time_for_tokens(6) == 20


def test_it_refuses_a_bucket_that_would_hold_nothing() -> None:
    with pytest.raises(InvalidArgumentError):
        _ = TokenBucket("t", 0, cycle=1, amount=1, timer=0)
