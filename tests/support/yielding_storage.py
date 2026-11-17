"""An in-memory storage that lets other tasks run inside every read and write."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, final

from xtr_rate_limiter import InMemoryStorage

if TYPE_CHECKING:
    from xtr_rate_limiter.limiter_state_interface import LimiterStateInterface

__all__ = ["YieldingStorage"]


@final
class YieldingStorage:
    """Counts in memory, switching to other tasks before every call.

    A store shared between processes answers over the network, so a
    reservation is switched away from between reading the state and writing
    it back; this one yields there to make that interleaving happen.
    """

    def __init__(self) -> None:
        self._inner = InMemoryStorage()

    async def save(self, state: LimiterStateInterface, /) -> None:
        await _yield()
        await self._inner.save(state)

    async def fetch(self, state_id: str, /) -> LimiterStateInterface | None:
        await _yield()
        return await self._inner.fetch(state_id)

    async def delete(self, state_id: str, /) -> None:
        await _yield()
        await self._inner.delete(state_id)


async def _yield() -> None:
    for _ in range(3):
        await asyncio.sleep(0)
