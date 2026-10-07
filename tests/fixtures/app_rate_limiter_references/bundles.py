"""The application's root bundles: only RateLimiterBundle, in every environment."""

from __future__ import annotations

from xtr_rate_limiter.bundle import RateLimiterBundle

BUNDLES = {RateLimiterBundle: {"all": True}}
