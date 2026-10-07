"""States kept in a cache pool, shared by every process that reaches it."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Final, final

from typing_extensions import override

from xtr_rate_limiter._time import instant
from xtr_rate_limiter.limiter_state_interface import LimiterStateInterface

from .storage_interface import StorageInterface

if TYPE_CHECKING:
    from xtr_cache_contracts import CacheItemPoolInterface

__all__ = ["CacheStorage"]

_KEY_PREFIX: Final = "rl."
"""What every key this storage takes starts with, so a shared pool stays apart."""


@final
class CacheStorage(StorageInterface):
    """Keeps states in a cache pool, each expiring with its state.

    States are stored under ``"rl."`` and a hash of their id, so any key a
    caller limits by — an address, an email — fits the pool's rules for keys
    and no other user of the pool can reach a limiter's count by accident.

    A cache never fails loudly: a pool that cannot reach its backend reads as
    empty and drops what it is given. A limiter on such a pool therefore lets
    every hit through while the backend is down — it fails open. Keep limits
    that must hold under that failure in Redis instead, where a failure is an
    error.

    A state goes in and comes back as an object, which a pool encodes with
    pickle by default: reading one runs code the stored bytes name. On a
    backend anything outside the application can write to — a Redis server
    shared with another tenant — give the pool a
    :class:`~xtr_cache.marshaller.SodiumMarshaller`, which refuses bytes it
    cannot authenticate before they ever reach pickle.
    """

    __slots__ = ("_pool",)

    def __init__(self, pool: CacheItemPoolInterface) -> None:
        """Keep states in ``pool``."""
        self._pool = pool

    @override
    async def save(self, state: LimiterStateInterface, /) -> None:
        """Store ``state``, expiring when it does."""
        item = await self._pool.get_item(_key(state.id))
        _ = item.set(state)
        if state.expires_at is not None:
            _ = item.expires_at(instant(state.expires_at))
        _ = await self._pool.save(item)

    @override
    async def fetch(self, state_id: str, /) -> LimiterStateInterface | None:
        """Return the state stored under ``state_id``; ``None`` for anything else."""
        value = (await self._pool.get_item(_key(state_id))).get()
        return value if isinstance(value, LimiterStateInterface) else None

    @override
    async def delete(self, state_id: str, /) -> None:
        """Remove the state stored under ``state_id``."""
        _ = await self._pool.delete_item(_key(state_id))


def _key(state_id: str) -> str:
    return f"{_KEY_PREFIX}{hashlib.sha1(state_id.encode(), usedforsecurity=False).hexdigest()}"
