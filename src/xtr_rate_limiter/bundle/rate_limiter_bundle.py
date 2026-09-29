"""The xtr-rate-limiter bundle: a limiter factory per configured name.

An application listing :class:`RateLimiterBundle` gets a
:class:`~xtr_rate_limiter.rate_limiter_factory_interface.RateLimiterFactoryInterface`
for every limiter of its :class:`RateLimiterConfig`, qualified by the
limiter's name, and a
:class:`~xtr_rate_limiter.rate_limiter_builder.RateLimiterBuilder` for limits
decided at runtime.

A limiter keeps its state in a cache pool by default — ``rate_limiter``,
which this bundle adds to the cache bundle's pools — and locks each change
through the lock bundle's default factory, so every process sharing the
pool shares the limit. Either peer joins when its package is installed;
without the lock bundle a limiter locks within its own process. A limiter
counting in Redis needs neither.

Nothing is opened until a factory is first asked for: no server reached.
Boot checks the configuration without opening anything — every storage is
one the bundle can build, every referenced service is registered — so a
mistake fails the application at startup rather than at its first hit. A
connection the bundle opened from a DSN is closed when the container is.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Final, final

from typing_extensions import override
from xtr_dependency_injection import (
    Bundle,
    ContainerBuilder,
    Reference,
    ServiceConfigurator,
    as_bundle,
    bundle_active,
    named_factory,
    required_bundle,
)
from xtr_service_contracts import ContainerInterface

from xtr_rate_limiter.compound_rate_limiter_factory import CompoundRateLimiterFactory
from xtr_rate_limiter.exception import InvalidArgumentError
from xtr_rate_limiter.limiter_config import (
    AUTO_LOCK,
    CACHE_STORAGE,
    DEFAULT_CACHE_POOL,
    IN_MEMORY_STORAGE,
    LimiterConfig,
)
from xtr_rate_limiter.rate_limiter_builder import RateLimiterBuilder
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
from .rate_limiter_config import RateLimiterConfig

if TYPE_CHECKING:
    from xtr_lock import LockFactory

__all__ = ["RateLimiterBundle"]

_DEFAULT_LOCK_RESOURCE: Final = "default"
"""The lock bundle's resource an ``"auto"`` lock uses."""

_CACHE_MISSING: Final = (
    'keeps its state in the "{pool}" cache pool, which the container does not provide: '
    'activate the cache bundle (install "xtr-rate-limiter[cache]" and xtr-cache), '
    'name a pool it has, or use another storage such as "in-memory"'
)

_UNKNOWN_STORAGE: Final = (
    'uses the storage "{storage}": expected "cache", "in-memory", a Redis DSN, '
    "or a Reference to a storage or a Redis client"
)


@final
@required_bundle("xtr_cache.bundle:CacheBundle", ignore_on_invalid=True)
@required_bundle("xtr_lock.bundle:LockBundle", ignore_on_invalid=True)
@as_bundle("rate_limiter", config=RateLimiterConfig)
class RateLimiterBundle(Bundle[RateLimiterConfig]):
    """Turns a :class:`RateLimiterConfig` into a limiter factory per name."""

    @override
    def prepend_extension(self, builder: ContainerBuilder) -> None:
        """When ``cache`` is active, give it the ``rate_limiter`` pool limiters keep their state in.

        The pool uses the cache's application adapter under a namespace of
        its own, so clearing another pool never resets a limit. An
        application declaring the pool itself keeps its own.
        """
        if not bundle_active(builder, "cache"):
            return
        # The cache is an optional peer, importable only once it is active.
        from xtr_cache.bundle import CacheConfig  # noqa: PLC0415
        from xtr_cache.bundle.pool_config import PoolConfig  # noqa: PLC0415

        def add_rate_limiter_pool(config: CacheConfig) -> CacheConfig:
            if DEFAULT_CACHE_POOL in config.pools:
                return config
            return replace(config, pools={**config.pools, DEFAULT_CACHE_POOL: PoolConfig()})

        builder.prepend_extension_config(CacheConfig, add_rate_limiter_pool)

    @override
    def load_extension(
        self,
        config: RateLimiterConfig,
        services: ServiceConfigurator,
        builder: ContainerBuilder,
    ) -> None:
        """Register a factory under each limiter's name, and the builder.

        Raises:
            InvalidArgumentError: When a limiter names a lock resource while
                the lock bundle is not active.
        """
        lock_active = bundle_active(builder, "lock")
        for name, limiter in config.limiters.items():
            factory = named_factory(_factory_of(name), f"rate_limiter_{name}")
            lock = None if limiter.policy in {"compound", "no_limit"} else limiter.lock
            _ = services.set(factory, qualifier=name).set_arguments(
                {
                    "config": limiter,
                    "redis_prefix": config.redis_prefix,
                    "lock_resource": _lock_resource(name, lock, lock_active),
                },
            )

        _ = services.set(_rate_limiter_builder).set_arguments(
            {
                "config": config.builder,
                "lock_resource": _lock_resource("builder", config.builder.lock, lock_active),
            },
        )

    @override
    async def boot(self) -> None:
        """Refuse a storage the bundle cannot build, or a service nobody registered, before any hit.

        The configuration is read resolved, so a storage given as
        ``env(...)`` is read here, and a variable that is not set fails the
        boot. The builder is checked only when it was pointed somewhere: its
        default needs the cache, which an application limiting nothing in
        code need not have.

        Raises:
            InvalidArgumentError: Naming the limiter whose storage is wrong.
        """
        container = self.container
        if container is None:  # pragma: no cover — the kernel sets this before boot.
            message = "RateLimiterBundle.boot ran without a container"
            raise RuntimeError(message)

        config = await container.get(RateLimiterConfig)
        for name, limiter in config.limiters.items():
            if limiter.policy not in {"compound", "no_limit"}:
                _check_storage(f'The "{name}" rate limiter', limiter, container)
        if config.builder != BuilderConfig():
            _check_storage("The rate limiter builder", config.builder, container)


def _lock_resource(name: str, lock: str | None, lock_active: bool) -> str | None:
    """Return the lock resource a limiter locks through; ``None`` for this process only.

    Raises:
        InvalidArgumentError: When ``lock`` names a resource while the lock
            bundle is not active.
    """
    if lock is None:
        return None
    if lock == AUTO_LOCK:
        return _DEFAULT_LOCK_RESOURCE if lock_active else None
    if not lock_active:
        raise InvalidArgumentError(
            f'The "{name}" rate limiter locks through the "{lock}" lock resource, '
            f"but the lock bundle is not active.",
        )
    return lock


def _check_storage(
    owner: str, config: LimiterConfig | BuilderConfig, container: ContainerInterface
) -> None:
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
    raise InvalidArgumentError(f"{owner} {_UNKNOWN_STORAGE.format(storage=storage)}.")


def _has_cache_pool(pool: str, container: ContainerInterface) -> bool:
    try:
        # The cache extra is optional.
        from xtr_cache_contracts import CacheItemPoolInterface  # noqa: PLC0415
    except ImportError:  # pragma: no cover — exercised only without the extra.
        return False
    return container.has(CacheItemPoolInterface, pool)


def _factory_of(
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
            yield RateLimiterFactory(
                name,
                config,
                _as_storage(owner, storage, target),
                await _lock_factory(lock_resource, container),
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
            await _storage(owner, config, container),
            await _lock_factory(lock_resource, container),
        )

    return rate_limiter


async def _rate_limiter_builder(
    config: BuilderConfig,
    lock_resource: str | None,
    container: ContainerInterface,
) -> RateLimiterBuilder:
    """Build the builder over the storage its configuration names."""
    owner = "The rate limiter builder"
    storage = config.storage
    if isinstance(storage, Reference):
        built = _as_storage(owner, storage, await storage.resolve(container))
    else:
        built = await _storage(owner, config, container)
    return RateLimiterBuilder(built, await _lock_factory(lock_resource, container))


async def _storage(
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
    raise InvalidArgumentError(f"{owner} {_UNKNOWN_STORAGE.format(storage=config.storage)}.")


def _as_storage(owner: str, reference: Reference, target: object) -> StorageInterface:
    if not isinstance(target, StorageInterface):
        raise InvalidArgumentError(
            f"{owner} uses {reference}, which is neither a rate limiter storage "
            f"nor a Redis client.",
        )
    return target


async def _lock_factory(
    lock_resource: str | None, container: ContainerInterface
) -> LockFactory | None:
    """Return the lock bundle's factory for ``lock_resource``; ``None`` for this process only."""
    if lock_resource is None:
        return None
    # Only named when the lock bundle is active, which proves the package installed.
    from xtr_lock import LockFactory  # noqa: PLC0415

    if not container.has(LockFactory, lock_resource):
        if lock_resource == _DEFAULT_LOCK_RESOURCE:
            return None
        raise InvalidArgumentError(
            f'A rate limiter locks through the "{lock_resource}" lock resource, '
            f"which the lock bundle does not configure.",
        )
    return await container.get(LockFactory, lock_resource)
