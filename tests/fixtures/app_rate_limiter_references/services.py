"""A service that is neither a rate limiter storage nor a Redis client."""

from __future__ import annotations

from xtr_dependency_injection import as_service

ODD = "odd"


class OddService:
    """Something a storage reference must refuse to accept."""


@as_service(qualifier=ODD)
def odd_service() -> OddService:
    return OddService()
