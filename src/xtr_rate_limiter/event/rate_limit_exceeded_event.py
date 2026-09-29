"""A caller turned a hit away because a limiter denied it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from xtr_event_dispatcher_contracts import Event

if TYPE_CHECKING:
    from xtr_rate_limiter.rate_limit import RateLimit

__all__ = ["RateLimitExceededEvent"]


@final
@dataclass(frozen=True, eq=False)
class RateLimitExceededEvent(Event):
    """A caller turned a hit away because a limiter denied it.

    A denied hit is not a rejection by itself — a caller may wait, retry or
    carry on — so limiters never dispatch this. Whoever turns the hit away
    does, such as a web route answering "too many requests".

    Attributes:
        rate_limit: The limit that denied the hit.
        limiter_name: The configured limiter's name, when known.
        key: The key that was consumed, when known, in whatever form the
            caller built it.
    """

    rate_limit: RateLimit
    limiter_name: str | None = None
    key: str | None = None
