from __future__ import annotations

import pytest
from redis.asyncio import Redis

from xtr_rate_limiter import InvalidArgumentError
from xtr_rate_limiter.redis.redis_connection import (
    create_redis_client,
    is_redis_client,
    is_redis_dsn,
    redis_installed,
)

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("dsn", ["redis://a", "REDISS://a", "valkey://a", "unix:///tmp/r.sock"])
def test_it_knows_a_redis_dsn(dsn: str) -> None:
    assert is_redis_dsn(dsn)


@pytest.mark.parametrize("dsn", ["cache", "in-memory", "memcached://a"])
def test_it_knows_what_is_not_one(dsn: str) -> None:
    assert not is_redis_dsn(dsn)


async def test_it_makes_a_client_that_connects_later() -> None:
    client = create_redis_client("valkey://localhost:6379/2")

    assert is_redis_client(client)
    assert redis_installed()
    assert not is_redis_client(object())
    await client.aclose()
    assert isinstance(client, Redis)


def test_it_refuses_another_scheme_without_echoing_credentials() -> None:
    with pytest.raises(InvalidArgumentError, match='"memcached"') as raised:
        _ = create_redis_client("memcached://user:secret@host")

    assert "secret" not in str(raised.value)
