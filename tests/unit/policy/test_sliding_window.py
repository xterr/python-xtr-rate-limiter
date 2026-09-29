from __future__ import annotations

import pytest

from xtr_rate_limiter import InvalidIntervalError
from xtr_rate_limiter.policy.sliding_window import SlidingWindow


def test_the_last_window_fades_out_as_the_current_one_passes() -> None:
    last = SlidingWindow("s", 100, now=0)
    last.add(8)

    current = SlidingWindow.from_previous_window(last, 100, now=125)
    current.add(3)

    # A quarter into the window: 0.75 * 8 + 3.
    assert current.hit_count(125) == 9
    assert current.expires_at == 300


def test_a_window_idle_for_more_than_a_window_carries_nothing() -> None:
    last = SlidingWindow("s", 100, now=0)
    last.add(8)

    current = SlidingWindow.from_previous_window(last, 100, now=250)

    assert current.hit_count(250) == 0
    assert current.is_expired(351)
    assert not current.is_expired(349)


def test_it_says_when_the_window_is_empty_and_when_tokens_come_free() -> None:
    window = SlidingWindow("s", 100, now=0)
    assert window.full_capacity_time(now=7) == 7

    window.add(4)
    assert window.full_capacity_time(now=0) == 175
    assert window.time_for_tokens(4, 1, now=50) > 0
    assert window.time_for_tokens(8, 1, now=50) == 0

    carried = SlidingWindow.from_previous_window(window, 100, now=120)
    assert carried.full_capacity_time(now=120) == 175
    assert carried.time_for_tokens(4, 4, now=120) > carried.time_for_tokens(4, 1, now=120)


def test_an_interval_must_be_positive() -> None:
    with pytest.raises(InvalidIntervalError):
        _ = SlidingWindow("s", 0, now=0)
