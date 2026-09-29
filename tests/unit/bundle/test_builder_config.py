from __future__ import annotations

import pytest

from xtr_rate_limiter import InvalidArgumentError
from xtr_rate_limiter.bundle import BuilderConfig


def test_it_builds_with_no_arguments() -> None:
    config = BuilderConfig()

    assert (config.storage, config.cache_pool, config.lock) == ("cache", "rate_limiter", "auto")


@pytest.mark.parametrize(
    "arguments",
    [{"storage": ""}, {"storage": 3}, {"cache_pool": ""}, {"lock": ""}],
)
def test_it_refuses_what_it_cannot_use(arguments: dict[str, object]) -> None:
    with pytest.raises(InvalidArgumentError):
        _ = BuilderConfig(**arguments)  # pyright: ignore[reportArgumentType]  # ty: ignore[invalid-argument-type]
