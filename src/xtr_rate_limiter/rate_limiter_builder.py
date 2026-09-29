"""Limiters built in code, one call per limit."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from .compound_rate_limiter_factory import CompoundRateLimiterFactory
from .limiter_config import LimiterConfig
from .policy.rate import Rate
from .rate_limiter_factory import RateLimiterFactory

if TYPE_CHECKING:
    from datetime import datetime

    from xtr_clock import ClockInterface
    from xtr_lock import LockFactory

    from ._interval import IntervalLike
    from .rate_limiter_factory_interface import RateLimiterFactoryInterface
    from .storage.storage_interface import StorageInterface

__all__ = ["RateLimiterBuilder"]


@final
class RateLimiterBuilder:
    """Builds limits in code, all kept in one storage.

    For a limit decided at runtime — per tenant, per plan — rather than
    written in configuration:

    ```python
    factory = builder.token_bucket(f"tenant-{tenant.id}", limit=tenant.burst, interval="1 second")
    limit = await factory.create(user_id).consume()
    ```
    """

    __slots__ = ("_clock", "_lock_factory", "_storage")

    def __init__(
        self,
        storage: StorageInterface,
        lock_factory: LockFactory | None = None,
        *,
        clock: ClockInterface | None = None,
    ) -> None:
        """Keep every limiter's state in ``storage``, locked through ``lock_factory``."""
        self._storage = storage
        self._lock_factory = lock_factory
        self._clock = clock

    def sliding_window(
        self, limiter_id: str, limit: int, interval: IntervalLike
    ) -> RateLimiterFactoryInterface:
        """Return at most ``limit`` hits in any span of ``interval``."""
        config = LimiterConfig("sliding_window", limit=limit, interval=interval)
        return self._factory(limiter_id, config)

    def fixed_window(
        self,
        limiter_id: str,
        limit: int,
        interval: IntervalLike,
        anchor_at: datetime | str | None = None,
    ) -> RateLimiterFactoryInterface:
        """Return at most ``limit`` hits per window of ``interval``, aligned to ``anchor_at``."""
        config = LimiterConfig("fixed_window", limit=limit, interval=interval, anchor_at=anchor_at)
        return self._factory(limiter_id, config)

    def token_bucket(
        self, limiter_id: str, limit: int, interval: IntervalLike, amount: int = 1
    ) -> RateLimiterFactoryInterface:
        """Return bursts of up to ``limit`` hits, ``amount`` tokens back every ``interval``."""
        config = LimiterConfig("token_bucket", limit=limit, rate=Rate(interval, amount))
        return self._factory(limiter_id, config)

    def compound(self, *factories: RateLimiterFactoryInterface) -> RateLimiterFactoryInterface:
        """Return every one of ``factories`` applied to each hit."""
        return CompoundRateLimiterFactory({str(index): f for index, f in enumerate(factories)})

    def noop(self) -> RateLimiterFactoryInterface:
        """Return no limit at all."""
        return self._factory("noop", LimiterConfig("no_limit"))

    def _factory(self, limiter_id: str, config: LimiterConfig) -> RateLimiterFactory:
        return RateLimiterFactory(
            limiter_id, config, self._storage, self._lock_factory, clock=self._clock
        )
