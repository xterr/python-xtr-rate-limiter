from __future__ import annotations

from xtr_rate_limiter.policy.window import Window


def test_hits_beyond_the_window_are_a_debt_the_next_windows_pay() -> None:
    window = Window("w", 10, 2, timer=0)
    window.add(5, now=0)

    assert window.available_tokens(0) == -3
    assert window.available_tokens(11) == -1
    assert window.available_tokens(21) == 1
    assert window.expires_at == 30


def test_a_window_rolls_over_carrying_what_it_still_owes() -> None:
    window = Window("w", 10, 2, timer=0)
    window.add(3, now=0)

    window.add(1, now=11)

    assert window.hit_count == 2
    assert window.available_tokens(11) == 0


def test_it_says_when_tokens_come_free_without_moving_with_the_clock() -> None:
    window = Window("w", 10, 2, timer=100)
    window.add(2, now=100)

    assert window.availability_time(1, now=105) == 110
    assert window.time_for_tokens(1, now=105) == 5
    assert window.time_for_tokens(1, now=115) == 0
    assert Window("fresh", 10, 2, timer=0).availability_time(2, now=3) == 3
