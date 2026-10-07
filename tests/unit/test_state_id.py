from __future__ import annotations

from xtr_rate_limiter._state_id import state_id


def test_it_prefixes_the_limit_name_with_its_length() -> None:
    assert state_id("api", "1.2.3.4") == "3:api:1.2.3.4"


def test_a_missing_key_leaves_the_key_empty() -> None:
    assert state_id("api", None) == "3:api:"
    assert state_id("api", "") == "3:api:"


def test_a_name_and_a_key_cannot_be_read_the_other_way_round() -> None:
    assert state_id("x", "a-b") != state_id("x-a", "b")
