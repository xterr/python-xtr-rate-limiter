"""Where a configured limiter keeps its state: boot checks and build errors."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar, final

import pytest
from typing_extensions import override
from xtr_dependency_injection import Reference
from xtr_service_contracts import ContainerInterface

from xtr_rate_limiter.bundle._storages import (
    DEFAULT_LOCK_RESOURCE,
    build_storage,
    check_storage,
    lock_factory,
    wrong_referent,
)
from xtr_rate_limiter.bundle.builder_config import BuilderConfig
from xtr_rate_limiter.exception import InvalidArgumentError
from xtr_rate_limiter.limiter_config import LimiterConfig

if TYPE_CHECKING:
    from collections.abc import Hashable

pytestmark = pytest.mark.anyio

_T = TypeVar("_T")


@final
class _EmptyContainer(ContainerInterface):
    """A container that provides nothing, for the refusal paths.

    Every lookup is empty, so ``_storages`` reaches its refusals: a storage it
    cannot build, a reference to nothing, a lock resource nobody configured.
    """

    @override
    async def get(self, service: type[_T], /, qualifier: Hashable | None = None) -> _T:
        del qualifier
        raise LookupError(service)

    @override
    def has(self, service: type[object], /, qualifier: Hashable | None = None) -> bool:
        del service, qualifier
        return False

    @override
    def get_parameter(self, name: str, /) -> object:
        raise LookupError(name)

    @override
    def has_parameter(self, name: str, /) -> bool:
        del name
        return False


def _window(storage: str | Reference) -> LimiterConfig:
    return LimiterConfig("fixed_window", limit=1, interval="1 minute", storage=storage)


def test_an_unknown_storage_reports_only_the_scheme_not_its_credentials() -> None:
    """A DSN nobody recognised may carry a password, and the error reaches logs
    and consoles; only its scheme is named."""
    container = _EmptyContainer()
    config = _window("mysql://user:s3cret@host:3306/db")

    with pytest.raises(InvalidArgumentError) as excinfo:
        check_storage('The "api" rate limiter', config, container)

    message = str(excinfo.value)
    assert "mysql://" in message
    assert "s3cret" not in message
    assert "user" not in message


def test_an_unknown_storage_with_no_scheme_reports_it_whole() -> None:
    """A value with no ``://`` carries no credentials to hide, so it is named."""
    container = _EmptyContainer()
    config = _window("nowhere")

    with pytest.raises(InvalidArgumentError) as excinfo:
        check_storage('The "api" rate limiter', config, container)

    assert 'storage "nowhere"' in str(excinfo.value)


async def test_building_an_unknown_storage_also_reports_only_the_scheme() -> None:
    """``build_storage`` reaches the same refusal when a factory is first asked."""
    container = _EmptyContainer()
    config = _window("mysql://user:s3cret@host:3306/db")

    with pytest.raises(InvalidArgumentError) as excinfo:
        _ = await build_storage('The "api" rate limiter', config, container)

    message = str(excinfo.value)
    assert "mysql://" in message
    assert "s3cret" not in message


def test_a_limiter_lists_redis_and_a_client_among_what_a_storage_takes() -> None:
    """A limiter may count in Redis itself, so its list names a Redis DSN and a
    client — which the builder's list does not."""
    container = _EmptyContainer()

    with pytest.raises(InvalidArgumentError) as excinfo:
        check_storage('The "api" rate limiter', _window("nowhere"), container)

    message = str(excinfo.value)
    assert "Redis DSN" in message
    assert "Redis client" in message


def test_the_builder_lists_neither_redis_nor_a_client() -> None:
    """The builder counts over a storage, never in Redis, so its list omits both."""
    container = _EmptyContainer()
    config = BuilderConfig(storage="nowhere")

    with pytest.raises(InvalidArgumentError) as excinfo:
        check_storage("The rate limiter builder", config, container)

    message = str(excinfo.value)
    assert "Redis" not in message


def test_wrong_referent_for_a_limiter_names_both_a_storage_and_a_redis_client() -> None:
    """A limiter reference may point at a storage or a Redis client, so the
    refusal of a wrong one names both."""
    reference = Reference(object, "something")

    error = wrong_referent('The "api" rate limiter', reference, _window(reference))

    message = str(error)
    assert "neither a rate limiter storage nor a Redis client" in message
    assert 'The "api" rate limiter' in message


def test_wrong_referent_for_the_builder_names_only_a_storage() -> None:
    """A builder reference may only point at a storage, so its refusal says just that."""
    reference = Reference(object, "something")
    config = BuilderConfig(storage=reference)

    error = wrong_referent("The rate limiter builder", reference, config)

    message = str(error)
    assert "not a rate limiter storage" in message
    assert "Redis client" not in message


async def test_the_default_lock_resource_is_optional_when_the_lock_bundle_is_absent() -> None:
    """The default resource falling back to this-process-only is how an "auto"
    lock works without the lock bundle active."""
    container = _EmptyContainer()

    factory = await lock_factory(DEFAULT_LOCK_RESOURCE, container)

    assert factory is None


async def test_no_lock_resource_locks_within_this_process() -> None:
    container = _EmptyContainer()

    assert await lock_factory(None, container) is None


async def test_a_named_lock_resource_the_bundle_does_not_configure_is_refused() -> None:
    """A resource the application named by hand, unlike the default, is a
    mistake worth failing the build for."""
    container = _EmptyContainer()

    with pytest.raises(InvalidArgumentError) as excinfo:
        _ = await lock_factory("strict", container)

    message = str(excinfo.value)
    assert '"strict"' in message
    assert "the lock bundle does not configure" in message
