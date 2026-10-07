from __future__ import annotations

import xtr_rate_limiter
from xtr_rate_limiter import limiter_config


def test_the_names_a_configuration_is_written_with_come_from_the_package() -> None:
    assert xtr_rate_limiter.AUTO_LOCK == limiter_config.AUTO_LOCK
    assert xtr_rate_limiter.CACHE_STORAGE == limiter_config.CACHE_STORAGE
    assert xtr_rate_limiter.IN_MEMORY_STORAGE == limiter_config.IN_MEMORY_STORAGE
    assert xtr_rate_limiter.DEFAULT_CACHE_POOL == limiter_config.DEFAULT_CACHE_POOL
    assert {"AUTO_LOCK", "CACHE_STORAGE", "IN_MEMORY_STORAGE", "DEFAULT_CACHE_POOL"} <= set(
        xtr_rate_limiter.__all__
    )
