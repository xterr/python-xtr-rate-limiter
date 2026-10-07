"""Where a configured limiter keeps its state: read at boot, built on first ask.

Every storage a limiter may be pointed at — a cache pool, this process's
memory, a Redis server, or a service somebody else registered — is checked
here at boot and built here when a factory is first requested, so the bundle
itself is left with the configuration it registers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Final

from xtr_dependency_injection import Reference
from xtr_service_contracts import ContainerInterface

from xtr_rate_limiter.compound_rate_limiter_factory import CompoundRateLimiterFactory
from xtr_rate_limiter.exception import InvalidArgumentError
from xtr_rate_limiter.limiter_config import CACHE_STORAGE, IN_MEMORY_STORAGE, LimiterConfig
from xtr_rate_limiter.rate_limiter_factory import RateLimiterFactory
from xtr_rate_limiter.rate_limiter_factory_interface import RateLimiterFactoryInterface
from xtr_rate_limiter.redis.redis_connection import (
    create_redis_client,
    is_redis_client,
    is_redis_dsn,
    redis_installed,
)
from xtr_rate_limiter.redis.redis_rate_limiter_factory import RedisRateLimiterFactory
from xtr_rate_limiter.storage.in_memory_storage import InMemoryStorage
from xtr_rate_limiter.storage.storage_interface import StorageInterface

from .builder_config import BuilderConfig

if TYPE_CHECKING:
    from xtr_lock import LockFactory

__all__ = [
    "DEFAULT_LOCK_RESOURCE",
    "build_storage",
    "check_storage",
    "factory_of",
    "lock_factory",
    "wrong_referent",
]

DEFAULT_LOCK_RESOURCE: Final = "default"
"""The lock bundle's resource an ``"auto"`` lock uses."""

_CACHE_MISSING: Final = (
    'keeps its state in the "{pool}" cache pool, which the container does not provide: '
    'activate the cache bundle (install "xtr-rate-limiter[cache]" and xtr-cache), '
    'name a pool it has, or use another storage such as "in-memory"'
)

_LIMITER_STORAGES: Final = (
    '"cache", "in-memory", a Redis DSN, or a Reference to a storage or a Redis client'
)
"""What a limiter's ``storage`` takes: a limiter may count on a Redis server itself."""

_BUILDER_STORAGES: Final = '"cache", "in-memory", or a Reference to a storage'
"""What the builder's ``storage`` takes: the builder counts over a storage, never in Redis."""

_LIMITER_REFERENT: Final = "neither a rate limiter storage nor a Redis client"
_BUILDER_REFERENT: Final = "not a rate limiter storage"


def check_storage(
    owner: str, config: LimiterConfig | BuilderConfig, container: ContainerInterface
) -> None:
    """Refuse a storage the bundle cannot build, or a service nobody registered.

    Raises:
        InvalidArgumentError: Naming ``owner`` and what is wrong with its storage.
    """
    storage = config.storage
    if isinstance(storage, Reference):
        if not storage.exists_in(container):
            raise InvalidArgumentError(
                f"{owner} uses {storage}, which the container does not provide.",
            )
        return
    if storage == IN_MEMORY_STORAGE:
        return
    if storage == CACHE_STORAGE:
        if not _has_cache_pool(config.cache_pool, container):
            raise InvalidArgumentError(f"{owner} {_CACHE_MISSING.format(pool=config.cache_pool)}.")
        return
    if is_redis_dsn(storage) and isinstance(config, LimiterConfig):
        if not redis_installed():  # pragma: no cover — exercised only without the extra.
            raise InvalidArgumentError(
                f'{owner} counts in Redis, which needs "xtr-rate-limiter[redis]".',
            )
        return
    raise _unknown_storage(owner, config)


def wrong_referent(
    owner: str, reference: Reference, config: LimiterConfig | BuilderConfig
) -> InvalidArgumentError:
    """Return the refusal of what ``reference`` points at, naming what it should."""
    accepted = _LIMITER_REFERENT if isinstance(config, LimiterConfig) else _BUILDER_REFERENT
    return InvalidArgumentError(f"{owner} uses {reference}, which is {accepted}.")


def factory_of(
    name: str,
) -> Callable[
    [LimiterConfig, str, str | None, ContainerInterface],
    AsyncIterator[RateLimiterFactoryInterface],
]:
    """Build the factory of ``name``'s limiter factory, closing a connection it opened.

    One function per limiter, so each carries its own name in the
    container's report.
    """

    async def rate_limiter(
        config: LimiterConfig,
        redis_prefix: str,
        lock_resource: str | None,
        container: ContainerInterface,
    ) -> AsyncIterator[RateLimiterFactoryInterface]:
        owner = f'The "{name}" rate limiter'
        if config.policy == "compound":
            factories = {
                combined: await container.get(RateLimiterFactoryInterface, combined)
                for combined in config.limiters
            }
            yield CompoundRateLimiterFactory(factories, config.keys)
            return
        if config.policy == "no_limit":
            yield RateLimiterFactory(name, config, InMemoryStorage())
            return

        storage = config.storage
        if isinstance(storage, Reference):
            target = await storage.resolve(container)
            if is_redis_client(target):
                yield RedisRateLimiterFactory(name, config, target, prefix=redis_prefix)
                return
            if not isinstance(target, StorageInterface):
                raise wrong_referent(owner, storage, config)
            yield RateLimiterFactory(
                name,
                config,
                target,
                await lock_factory(lock_resource, container),
            )
            return

        if is_redis_dsn(storage):
            client = create_redis_client(storage)
            try:
                yield RedisRateLimiterFactory(name, config, client, prefix=redis_prefix)
            finally:
                await client.aclose()
            return

        yield RateLimiterFactory(
            name,
            config,
            await build_storage(owner, config, container),
            await lock_factory(lock_resource, container),
        )

    return rate_limiter


async def build_storage(
    owner: str, config: LimiterConfig | BuilderConfig, container: ContainerInterface
) -> StorageInterface:
    """Build the ``"cache"`` or ``"in-memory"`` storage ``config`` names."""
    if config.storage == IN_MEMORY_STORAGE:
        return InMemoryStorage()
    if config.storage == CACHE_STORAGE:
        if not _has_cache_pool(config.cache_pool, container):
            raise InvalidArgumentError(f"{owner} {_CACHE_MISSING.format(pool=config.cache_pool)}.")
        # The cache extra is optional; a pool proves it installed.
        from xtr_cache_contracts import CacheItemPoolInterface  # noqa: PLC0415

        from xtr_rate_limiter.storage.cache_storage import CacheStorage  # noqa: PLC0415

        return CacheStorage(await container.get(CacheItemPoolInterface, config.cache_pool))
    raise _unknown_storage(owner, config)


async def lock_factory(
    lock_resource: str | None, container: ContainerInterface
) -> LockFactory | None:
    """Return the lock bundle's factory for ``lock_resource``; ``None`` for this process only."""
    if lock_resource is None:
        return None
    # Only named when the lock bundle is active, which proves the package installed.
    from xtr_lock import LockFactory  # noqa: PLC0415

    if not container.has(LockFactory, lock_resource):
        if lock_resource == DEFAULT_LOCK_RESOURCE:
            return None
        raise InvalidArgumentError(
            f'A rate limiter locks through the "{lock_resource}" lock resource, '
            f"which the lock bundle does not configure.",
        )
    return await container.get(LockFactory, lock_resource)


def _unknown_storage(owner: str, config: LimiterConfig | BuilderConfig) -> InvalidArgumentError:
    """Return the refusal of ``config``'s storage, listing what it does take.

    Only the scheme of what was given is reported: a DSN nobody recognised
    may still carry a password, and the error reaches logs and consoles.
    """
    scheme, separator, _ = f"{config.storage}".partition("://")
    reported = f"{scheme}{separator}" if separator else scheme
    accepted = _LIMITER_STORAGES if isinstance(config, LimiterConfig) else _BUILDER_STORAGES
    return InvalidArgumentError(
        f'{owner} uses the storage "{reported}": expected {accepted}.',
    )


def _has_cache_pool(pool: str, container: ContainerInterface) -> bool:
    try:
        # The cache extra is optional.
        from xtr_cache_contracts import CacheItemPoolInterface  # noqa: PLC0415
    except ImportError:  # pragma: no cover — exercised only without the extra.
        return False
    return container.has(CacheItemPoolInterface, pool)
