from __future__ import annotations

import pytest
from xtr_dependency_injection.testing import assert_zero_config

from xtr_rate_limiter.bundle import RateLimiterBundle

pytestmark = pytest.mark.anyio


async def test_it_builds_and_boots_with_no_configuration() -> None:
    await assert_zero_config(RateLimiterBundle)
