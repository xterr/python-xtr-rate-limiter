from __future__ import annotations

from xtr_rate_limiter.policy.calendar_aligned_window import CalendarAlignedWindow


def test_it_counts_hits_until_the_period_ends() -> None:
    window = CalendarAlignedWindow("c", 2, period_start=0, period_end=100)
    window.add(2)

    assert window.hit_count == 2
    assert window.available_tokens() == 0
    assert window.availability_time(1, now=40) == 100
    assert window.time_for_tokens(1, now=40) == 60
    assert window.availability_time(0, now=40) == 40
    assert (window.period_start, window.period_end, window.expires_at) == (0, 100, 100)
