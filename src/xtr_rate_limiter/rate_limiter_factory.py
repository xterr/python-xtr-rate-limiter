"""One configured limit, handing out a limiter per key over a storage."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, final

from typing_extensions import override
from xtr_clock import Clock

from ._lock import lock_for
from .exception import InvalidArgumentError
from .policy.fixed_window_limiter import FixedWindowLimiter
from .policy.no_limiter import NoLimiter
from .policy.sliding_window_limiter import SlidingWindowLimiter
from .policy.token_bucket_limiter import TokenBucketLimiter
from .rate_limiter_factory_interface import RateLimiterFactoryInterface

if TYPE_CHECKING:
    from xtr_clock import ClockInterface
    from xtr_lock import LockFactory

    from ._interval import Interval
    from .limiter_config import LimiterConfig
    from .limiter_interface import LimiterInterface
    from .storage.storage_interface import StorageInterface

__all__ = ["RateLimiterFactory"]


@final
class RateLimiterFactory(RateLimiterFactoryInterface):
    """Hands out limiters for one limit, keeping their state in ``storage``.

    Each limiter's state is kept under ``"<id>-<key>"``. Its read and write
    happen under a lock on that name, taken from ``lock_factory`` — so
    processes sharing the storage also share the lock — or held within this
    process when there is none.

    ```python
    factory = RateLimiterFactory(
        "api",
        LimiterConfig("sliding_window", limit=100, interval="1 minute"),
        InMemoryStorage(),
    )
    limit = await factory.create(client_ip).consume()
    ```
    """

    __slots__ = ("_anchor", "_clock", "_config", "_id", "_interval", "_lock_factory", "_storage")

    def __init__(
        self,
        limiter_id: str,
        config: LimiterConfig,
        storage: StorageInterface,
        lock_factory: LockFactory | None = None,
        *,
        clock: ClockInterface | None = None,
    ) -> None:
        """Build limiters counting as ``config`` says, named ``limiter_id``.

        ``config``'s storage and lock fields are the bundle's to read; here
        the storage and the lock factory are given.

        Raises:
            InvalidArgumentError: When ``config`` is a compound limiter —
                that is a :class:`~xtr_rate_limiter.CompoundRateLimiterFactory`.
        """
        if config.policy == "compound":
            raise InvalidArgumentError(
                "A compound rate limiter combines factories: build a CompoundRateLimiterFactory.",
            )
        self._id = limiter_id
        self._config = config
        self._storage = storage
        self._lock_factory = lock_factory
        self._clock: ClockInterface = clock if clock is not None else Clock()
        # Read once: a factory hands out a limiter per request.
        self._interval = None if config.interval is None else config.parsed_interval()
        self._anchor = config.anchor()

    @override
    def create(self, key: str | None = None) -> LimiterInterface:
        """Return the limiter counting the hits of ``key``."""
        config = self._config
        if config.policy == "no_limit" or config.limit is None:
            return NoLimiter(self._clock)

        state_id = f"{self._id}-{key or ''}"
        lock = lock_for(state_id, self._lock_factory)
        if config.rate is not None:
            return TokenBucketLimiter(
                state_id, config.limit, config.rate, self._storage, lock, clock=self._clock
            )
        # Only windows are left, and a window's config always has an interval.
        interval = cast("Interval", self._interval)
        if config.policy == "sliding_window":
            return SlidingWindowLimiter(
                state_id, config.limit, interval, self._storage, lock, clock=self._clock
            )
        return FixedWindowLimiter(
            state_id,
            config.limit,
            interval,
            self._storage,
            lock,
            anchor_at=self._anchor,
            clock=self._clock,
        )
