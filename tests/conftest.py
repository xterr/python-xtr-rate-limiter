"""Shared test fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from fakeredis import FakeAsyncRedis, FakeServer
from xtr_clock import Clock, MockClock

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Generator


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _isolate_clock() -> Generator[None, None, None]:
    """Keep a test that installs a clock from reaching the next one."""
    with Clock.using(Clock.get()):
        yield


@pytest.fixture
def clock() -> MockClock:
    """A clock frozen mid-January, moved only by the test."""
    return MockClock(datetime(2026, 1, 15, 12, 0, tzinfo=UTC))


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeAsyncRedis]:
    """Yield a client on a Redis server of its own, in this process, running the scripts."""
    client = FakeAsyncRedis(server=FakeServer())
    try:
        yield client
    finally:
        await client.aclose()
