from __future__ import annotations

from datetime import UTC, datetime

from xtr_clock import DatePoint

from xtr_rate_limiter._time import instant


def test_an_instant_is_a_utc_date_point() -> None:
    moment = instant(0)

    assert isinstance(moment, DatePoint)
    assert moment == datetime(1970, 1, 1, tzinfo=UTC)
