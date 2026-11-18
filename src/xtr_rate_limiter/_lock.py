"""The lock a limiter holds while it reads, changes and writes back its state.

A limiter reads its state, works out the answer and writes the state back.
Two callers doing that at once for one key would both read the same state
and both be granted the same tokens, so the three steps run under a lock
per key: within this process always — a task can be switched away from at
every ``await`` between the read and the write — and, when the state is
shared between processes, a lock from a lock factory too.
"""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Final, Protocol, final
from weakref import WeakKeyDictionary, WeakValueDictionary

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from contextlib import AbstractAsyncContextManager

    from xtr_lock import LockFactory

__all__ = ["LimiterLock", "LocalLock", "SharedLock", "lock_for"]


class LimiterLock(Protocol):
    """What a limiter needs of a lock: hold it for one read-modify-write."""

    def hold(self) -> AbstractAsyncContextManager[None]:
        """Wait for the lock, and hold it until the block is left."""
        ...


_LOCAL: Final[
    WeakKeyDictionary[asyncio.AbstractEventLoop, WeakValueDictionary[str, asyncio.Lock]]
] = WeakKeyDictionary()
"""One lock per id and event loop, kept only while some task holds or awaits it.

Keyed by the loop as well as the id: an :class:`asyncio.Lock` belongs to the
loop it was first awaited on, so an id reused on another loop — a second
:func:`asyncio.run`, say — is given a lock of its own there.
"""

_LOCAL_GUARD: Final = threading.Lock()
"""Held while the lock table is read and written, never across an await.

Loops in other threads reach the same table; two of them arriving on one id
must not each create its entry.
"""


def _local_lock(resource: str) -> asyncio.Lock:
    """Return the lock every limiter of ``resource`` on the running loop shares."""
    loop = asyncio.get_running_loop()
    with _LOCAL_GUARD:
        for closed in [existing for existing in _LOCAL if existing.is_closed()]:
            del _LOCAL[closed]
        by_id = _LOCAL.get(loop)
        if by_id is None:
            by_id = _LOCAL[loop] = WeakValueDictionary()
        lock = by_id.get(resource)
        if lock is None:
            lock = by_id[resource] = asyncio.Lock()
        return lock


@final
class LocalLock:
    """A lock on one id, shared by every limiter of this process acting on it."""

    __slots__ = ("_resource",)

    def __init__(self, resource: str) -> None:
        """Lock ``resource`` together with every other limiter on it."""
        self._resource = resource

    @asynccontextmanager
    async def hold(self) -> AsyncGenerator[None]:
        """Wait for the tasks of this process holding the id, then hold it."""
        async with _local_lock(self._resource):
            yield


@final
class SharedLock:
    """A lock on one id, shared with every process locking through one lock factory.

    Every hold is a holder of its own: a lock is made from the factory each
    time, since locks made for one key act as one holder and would not keep
    two reservations of this process apart. The in-process lock is taken
    first, so the tasks of this process queue here rather than polling a
    store that cannot wait on their behalf.
    """

    __slots__ = ("_local", "_lock_factory", "_resource")

    def __init__(self, resource: str, lock_factory: LockFactory) -> None:
        """Lock ``resource`` through ``lock_factory``, and within this process."""
        self._resource = resource
        self._lock_factory = lock_factory
        self._local = LocalLock(resource)

    @asynccontextmanager
    async def hold(self) -> AsyncGenerator[None]:
        """Hold the id within this process, then in the factory's store."""
        async with self._local.hold():
            lock = self._lock_factory.create_lock(self._resource)
            _ = await lock.acquire(blocking=True)
            try:
                yield
            finally:
                await lock.release()


def lock_for(resource: str, lock_factory: LockFactory | None) -> LimiterLock:
    """Return the lock on ``resource``: through ``lock_factory``, or within this process."""
    if lock_factory is None:
        return LocalLock(resource)
    return SharedLock(resource, lock_factory)
