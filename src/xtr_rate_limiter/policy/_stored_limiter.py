"""What every limiter keeping its state in a storage shares."""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, ClassVar

from typing_extensions import override

from xtr_rate_limiter.exception import InvalidArgumentError, MaxWaitDurationExceededError
from xtr_rate_limiter.limiter_interface import LimiterInterface

if TYPE_CHECKING:
    from xtr_clock import ClockInterface

    from xtr_rate_limiter._lock import LimiterLock
    from xtr_rate_limiter.rate_limit import RateLimit
    from xtr_rate_limiter.reservation import Reservation
    from xtr_rate_limiter.storage.storage_interface import StorageInterface

__all__ = ["StoredLimiter"]


class StoredLimiter(LimiterInterface, metaclass=ABCMeta):
    """A limiter whose state lives in a storage, changed under a lock on its id."""

    __slots__: ClassVar[tuple[str, ...]] = ("_clock", "_id", "_lock", "_storage")

    _id: str
    _storage: StorageInterface
    _lock: LimiterLock
    _clock: ClockInterface

    def __init__(
        self,
        state_id: str,
        storage: StorageInterface,
        lock: LimiterLock,
        clock: ClockInterface,
    ) -> None:
        self._id = state_id
        self._storage = storage
        self._lock = lock
        self._clock = clock

    @override
    async def consume(self, tokens: int = 1) -> RateLimit:
        """Spend ``tokens`` now if they are available; spend nothing otherwise."""
        try:
            return (await self.reserve(tokens, 0)).rate_limit
        except MaxWaitDurationExceededError as error:
            return error.rate_limit

    @override
    async def reset(self) -> None:
        """Forget every hit counted for this key."""
        _ = await self._lock.acquire(blocking=True)
        try:
            await self._storage.delete(self._id)
        finally:
            await self._lock.release()

    @override
    async def reserve(self, tokens: int = 1, max_time: float | None = None) -> Reservation:
        """Book ``tokens`` under the lock on this limiter's id."""
        _ = await self._lock.acquire(blocking=True)
        try:
            return await self._reserve(tokens, max_time)
        finally:
            await self._lock.release()

    @abstractmethod
    async def _reserve(self, tokens: int, max_time: float | None) -> Reservation:
        """Read the state, decide, and write it back; the lock is held."""


def check_tokens(tokens: int, limit: int, what: str) -> None:
    """Refuse a negative number of tokens, or more than the limiter ever holds.

    Raises:
        InvalidArgumentError: Naming ``what`` the limit is.
    """
    if tokens < 0:
        raise InvalidArgumentError(f"Cannot reserve a negative number of tokens ({tokens}).")
    if tokens > limit:
        raise InvalidArgumentError(
            f"Cannot reserve more tokens ({tokens}) than the {what} of the rate limiter ({limit}).",
        )


def check_limit(limit: int) -> None:
    """Refuse a limit that would never accept a hit.

    Raises:
        InvalidArgumentError: When ``limit`` is below one.
    """
    if limit < 1:
        raise InvalidArgumentError(
            f"Cannot set the limit to {limit}, as that would never accept any hit.",
        )
