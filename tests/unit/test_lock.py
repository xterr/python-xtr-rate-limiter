from __future__ import annotations

import asyncio

import pytest

from xtr_rate_limiter._lock import LocalLock, lock_for

pytestmark = pytest.mark.anyio


async def test_limiters_of_one_id_share_their_lock() -> None:
    first = LocalLock("a")
    second = lock_for("a", None)
    other = LocalLock("b")

    assert await first.acquire()
    assert not await second.acquire()
    assert await other.acquire()

    waiting = asyncio.create_task(second.acquire(blocking=True))
    await asyncio.sleep(0)
    await first.release()

    assert await waiting
    await second.release()
    await other.release()
