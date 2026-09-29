from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from xtr_rate_limiter import RateLimit, Reservation
from xtr_rate_limiter._time import instant

if TYPE_CHECKING:
    from xtr_clock import MockClock

pytestmark = pytest.mark.anyio


async def test_a_reservation_waits_until_its_time(clock: MockClock) -> None:
    now = clock.now().timestamp()
    limit = RateLimit(0, instant(now + 12), accepted=False, limit=1, clock=clock)
    reservation = Reservation(now + 12, limit, clock=clock)

    assert reservation.wait_duration() == pytest.approx(12)
    await reservation.wait()

    assert reservation.wait_duration() == 0
    assert reservation.rate_limit is limit
    assert repr(reservation).startswith("Reservation(time_to_act=")
