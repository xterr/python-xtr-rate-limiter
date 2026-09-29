from __future__ import annotations

import pytest

from xtr_rate_limiter import InvalidArgumentError
from xtr_rate_limiter.policy._stored_limiter import check_limit, check_tokens


@pytest.mark.parametrize(("tokens", "match"), [(-1, "negative"), (3, "more tokens")])
def test_it_refuses_tokens_it_could_never_hold(tokens: int, match: str) -> None:
    with pytest.raises(InvalidArgumentError, match=match):
        check_tokens(tokens, 2, "size")


def test_it_refuses_a_limit_that_would_accept_nothing() -> None:
    check_limit(1)
    with pytest.raises(InvalidArgumentError):
        check_limit(0)
