"""End-to-end: an application listing RateLimiterBundle limits through what it configured."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from xtr_cache_contracts import CacheItemPoolInterface
from xtr_dependency_injection import Kernel
from xtr_dependency_injection.exception import ServiceResolutionError

from xtr_rate_limiter import (
    CompoundRateLimiterFactory,
    InvalidArgumentError,
    RateLimiterBuilder,
    RateLimiterFactory,
    RateLimiterFactoryInterface,
)
from xtr_rate_limiter.redis import RedisRateLimiterFactory

if TYPE_CHECKING:
    from collections.abc import Mapping

pytestmark = pytest.mark.anyio

APP = "tests.fixtures.app_rate_limiter"
REFERENCES_APP = "tests.fixtures.app_rate_limiter_references"

_ENVIRON: Mapping[str, str] = {
    "RL_LOGIN_STORAGE": "cache",
    "RL_REDIS_DSN": "redis://localhost:6379/15",
    "RL_BUILDER_STORAGE": "in-memory",
}


def _kernel(**environ: str) -> Kernel:
    return Kernel(APP, env="test", environ={**_ENVIRON, **environ})


async def test_each_limiter_is_provided_under_its_name() -> None:
    async with await _kernel().boot() as booted:
        container = booted.container
        factories = {
            name: await container.get(RateLimiterFactoryInterface, name)
            for name in ("api", "login", "uploads", "local", "custom", "open", "dsn")
        }
        atomic = await container.get(RateLimiterFactoryInterface, "atomic")
        strict = await container.get(RateLimiterFactoryInterface, "strict")

        assert all(isinstance(f, RateLimiterFactory) for n, f in factories.items() if n != "dsn")
        assert isinstance(factories["dsn"], RedisRateLimiterFactory)
        assert isinstance(atomic, RedisRateLimiterFactory)
        assert isinstance(strict, CompoundRateLimiterFactory)

        for name in ("login", "uploads", "local", "custom"):
            limiter = factories[name].create("alice")
            assert (await limiter.consume()).is_accepted(), name
            assert not (await limiter.consume()).is_accepted(), name
        assert (await atomic.create("alice").consume()).is_accepted()
        assert not (await atomic.create("alice").consume()).is_accepted()
        assert (await factories["open"].create().consume(1_000)).is_accepted()


async def test_a_compound_limiter_applies_every_limit() -> None:
    async with await _kernel().boot() as booted:
        strict = await booted.container.get(RateLimiterFactoryInterface, "strict")

        assert (await strict.create("a").consume()).is_accepted()
        assert not (await strict.create("a").consume()).is_accepted()


async def test_a_cache_limiter_keeps_its_state_in_the_rate_limiter_pool() -> None:
    async with await _kernel().boot() as booted:
        login = await booted.container.get(RateLimiterFactoryInterface, "login")
        _ = await login.create("alice").consume()

        pool = await booted.container.get(CacheItemPoolInterface, "rate_limiter")
        assert await pool.clear()
        assert (await login.create("alice").consume()).is_accepted()


async def test_the_builder_counts_over_its_configured_storage() -> None:
    async with await _kernel().boot() as booted:
        builder = await booted.container.get(RateLimiterBuilder)
        factory = builder.fixed_window("tenant-1", 1, "1 minute")

        assert (await factory.create("a").consume()).is_accepted()
        assert not (await factory.create("a").consume()).is_accepted()


@pytest.mark.parametrize(
    ("variable", "value", "message"),
    [
        ("RL_LOGIN_STORAGE", "nowhere", 'uses the storage "nowhere"'),
        ("RL_BUILDER_STORAGE", "redis://localhost", "rate limiter builder uses the storage"),
    ],
)
async def test_boot_refuses_a_storage_it_cannot_build(
    variable: str, value: str, message: str
) -> None:
    with pytest.raises(InvalidArgumentError, match=message):
        async with await _kernel(**{variable: value}).boot():
            pass


async def test_a_refused_storage_is_reported_down_to_its_scheme() -> None:
    dsn = "postgres://admin:s3cret@db.internal:5432/limits"

    with pytest.raises(InvalidArgumentError) as raised:
        async with await _kernel(RL_LOGIN_STORAGE=dsn).boot():
            pass

    reported = str(raised.value)
    assert 'uses the storage "postgres://"' in reported
    assert "s3cret" not in reported
    assert "db.internal" not in reported


async def test_a_limiter_and_the_builder_each_list_the_storages_they_take() -> None:
    with pytest.raises(InvalidArgumentError) as limiter:
        async with await _kernel(RL_LOGIN_STORAGE="nowhere").boot():
            pass
    with pytest.raises(InvalidArgumentError) as builder:
        async with await _kernel(RL_BUILDER_STORAGE="nowhere").boot():
            pass

    assert "a Redis DSN" in str(limiter.value)
    assert "a Redis client" in str(limiter.value)
    assert "a Redis DSN" not in str(builder.value)
    assert "a Redis client" not in str(builder.value)
    assert "a Reference to a storage" in str(builder.value)


async def test_a_reference_to_something_else_names_what_it_should_point_at() -> None:
    async with await Kernel(REFERENCES_APP, env="test").boot() as booted:
        with pytest.raises(ServiceResolutionError) as limiter:
            _ = await booted.container.get(RateLimiterFactoryInterface, "wrong")
        with pytest.raises(ServiceResolutionError) as builder:
            _ = await booted.container.get(RateLimiterBuilder)

        assert isinstance(limiter.value.__cause__, InvalidArgumentError)
        assert isinstance(builder.value.__cause__, InvalidArgumentError)
        assert "is neither a rate limiter storage nor a Redis client" in str(limiter.value)
        assert "is not a rate limiter storage" in str(builder.value)
