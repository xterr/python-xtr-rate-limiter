from __future__ import annotations

import pytest

from xtr_rate_limiter.redis._scripts import (
    ANCHORED_FIXED_WINDOW,
    FIXED_WINDOW,
    SLIDING_WINDOW,
    TOKEN_BUCKET,
)


@pytest.mark.parametrize(
    "script", [ANCHORED_FIXED_WINDOW, FIXED_WINDOW, SLIDING_WINDOW, TOKEN_BUCKET]
)
def test_every_script_reads_the_server_clock_only_when_not_sent_one(script: str) -> None:
    assert 'redis.call("TIME")' in script
    assert "if now == nil then" in script
