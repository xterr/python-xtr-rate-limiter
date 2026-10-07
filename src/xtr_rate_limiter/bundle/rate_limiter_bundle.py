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

from dataclasses import replace
from typing import final

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

from xtr_rate_limiter.exception import InvalidArgumentError
from xtr_rate_limiter.limiter_config import (
    AUTO_LOCK,
    DEFAULT_CACHE_POOL,
)
from xtr_rate_limiter.rate_limiter_builder import RateLimiterBuilder
from xtr_rate_limiter.storage.storage_interface import StorageInterface

from ._storages import (
    DEFAULT_LOCK_RESOURCE,
    build_storage,
    check_storage,
    factory_of,
    lock_factory,
    wrong_referent,
)
from .builder_config import BuilderConfig
from .rate_limiter_config import RateLimiterConfig

__all__ = ["RateLimiterBundle"]


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
            factory = named_factory(factory_of(name), f"rate_limiter_{name}")
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
                check_storage(f'The "{name}" rate limiter', limiter, container)
        if config.builder != BuilderConfig():
            check_storage("The rate limiter builder", config.builder, container)


def _lock_resource(name: str, lock: str | None, lock_active: bool) -> str | None:
    """Return the lock resource a limiter locks through; ``None`` for this process only.

    Raises:
        InvalidArgumentError: When ``lock`` names a resource while the lock
            bundle is not active.
    """
    if lock is None:
        return None
    if lock == AUTO_LOCK:
        return DEFAULT_LOCK_RESOURCE if lock_active else None
    if not lock_active:
        raise InvalidArgumentError(
            f'The "{name}" rate limiter locks through the "{lock}" lock resource, '
            f"but the lock bundle is not active.",
        )
    return lock


async def _rate_limiter_builder(
    config: BuilderConfig,
    lock_resource: str | None,
    container: ContainerInterface,
) -> RateLimiterBuilder:
    """Build the builder over the storage its configuration names."""
    owner = "The rate limiter builder"
    storage = config.storage
    if isinstance(storage, Reference):
        target = await storage.resolve(container)
        if not isinstance(target, StorageInterface):
            raise wrong_referent(owner, storage, config)
        built = target
    else:
        built = await build_storage(owner, config, container)
    return RateLimiterBuilder(built, await lock_factory(lock_resource, container))
