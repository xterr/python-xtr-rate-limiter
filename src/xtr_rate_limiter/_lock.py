"""The lock a limiter holds while it reads, changes and writes back its state.

A limiter reads its state, works out the answer and writes the state back.
Two callers doing that at once for one key would both read the same state
and both be granted the same tokens, so the three steps run under a lock
per key: one from a lock factory when the state is shared between
processes, or, without one, a lock held within this process — which is
already needed there, since a task can be switched away from at every
``await`` between the read and the write.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Final, Protocol, final
from weakref import WeakValueDictionary

if TYPE_CHECKING:
    from xtr_lock import LockFactory

__all__ = ["LimiterLock", "LocalLock", "lock_for"]


class LimiterLock(Protocol):
    """What a limiter needs of a lock: take it, waiting, and let it go."""

    async def acquire(self, blocking: bool = False) -> bool:
        """Take the lock; with ``blocking``, wait until it can be taken."""
        ...

    async def release(self) -> None:
        """Let the lock go."""
        ...


_LOCAL: Final[WeakValueDictionary[str, asyncio.Lock]] = WeakValueDictionary()
"""One lock per id, kept only while some limiter still holds on to it."""


@final
class LocalLock:
    """A lock on one id, shared by every limiter of this process acting on it."""

    __slots__ = ("_lock",)

    def __init__(self, resource: str) -> None:
        """Share the lock of ``resource`` with every other limiter on it."""
        lock = _LOCAL.get(resource)
        if lock is None:
            lock = asyncio.Lock()
            _LOCAL[resource] = lock
        self._lock = lock

    async def acquire(self, blocking: bool = False) -> bool:
        """Take the lock; with ``blocking``, wait for the task holding it."""
        if not blocking and self._lock.locked():
            return False
        _ = await self._lock.acquire()
        return True

    async def release(self) -> None:
        """Let the lock go."""
        self._lock.release()


def lock_for(resource: str, lock_factory: LockFactory | None) -> LimiterLock:
    """Return the lock on ``resource``: from ``lock_factory``, or within this process."""
    if lock_factory is None:
        return LocalLock(resource)
    return lock_factory.create_lock(resource)
