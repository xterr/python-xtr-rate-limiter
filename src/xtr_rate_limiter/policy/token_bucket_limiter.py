"""Limits hits to what a bucket holds, refilled at a steady rate."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, final

from typing_extensions import override
from xtr_clock import Clock

from xtr_rate_limiter._time import instant
from xtr_rate_limiter.exception import MaxWaitDurationExceededError
from xtr_rate_limiter.rate_limit import RateLimit
from xtr_rate_limiter.reservation import Reservation

from ._stored_limiter import StoredLimiter, check_limit, check_tokens
from .token_bucket import TokenBucket

if TYPE_CHECKING:
    from xtr_clock import ClockInterface

    from xtr_rate_limiter._lock import LimiterLock
    from xtr_rate_limiter.storage.storage_interface import StorageInterface

    from .rate import Rate

__all__ = ["TokenBucketLimiter"]


@final
class TokenBucketLimiter(StoredLimiter):
    """Bursts of up to ``max_burst`` hits, then a steady ``rate``.

    Each hit takes a token from a bucket holding at most ``max_burst``; the
    ``rate`` puts tokens back. An idle caller can burst, a busy one settles
    to the rate.
    """

    __slots__: ClassVar[tuple[str, ...]] = ("_amount", "_cycle", "_max_burst")

    def __init__(  # noqa: PLR0913 — every option past the lock is keyword-only.
        self,
        state_id: str,
        max_burst: int,
        rate: Rate,
        storage: StorageInterface,
        lock: LimiterLock,
        *,
        clock: ClockInterface | None = None,
    ) -> None:
        """Limit ``state_id`` to bursts of ``max_burst``, refilled at ``rate``.

        Raises:
            InvalidArgumentError: When ``max_burst`` is below one.
        """
        check_limit(max_burst)
        resolved: ClockInterface = clock if clock is not None else Clock()
        super().__init__(state_id, storage, lock, resolved)
        self._max_burst = max_burst
        self._cycle = rate.cycle_from(resolved.now().timestamp())
        self._amount = rate.amount

    @override
    async def _reserve(self, tokens: int, max_time: float | None) -> Reservation:
        check_tokens(tokens, self._max_burst, "burst size")
        now = self._clock.now().timestamp()
        stored = await self._storage.fetch(self._id)
        bucket = (
            stored
            if isinstance(stored, TokenBucket)
            else TokenBucket(self._id, self._max_burst, self._cycle, self._amount, now)
        )

        available = min(bucket.available_tokens(now), self._max_burst)
        if available >= tokens:
            bucket.set_tokens(available - tokens, now)
            retry_after = now + self._time_for_tokens(1) if available == tokens else now
            limit = self._rate_limit(
                bucket.available_tokens(now),
                available - tokens,
                now,
                retry_after=retry_after,
                accepted=True,
            )
            reservation = Reservation(now, limit, clock=self._clock)
        else:
            wait = self._time_for_tokens(tokens - available)
            if max_time is not None and wait > max_time:
                rejected = self._rate_limit(
                    available, available, now, retry_after=now + wait, accepted=False
                )
                raise MaxWaitDurationExceededError(wait, max_time, rejected)
            # Every token until then is booked for this caller: none is left for anyone else.
            bucket.set_tokens(available - tokens, now)
            limit = self._rate_limit(
                0, available - tokens, now, retry_after=now + wait, accepted=False
            )
            reservation = Reservation(now + wait, limit, clock=self._clock)

        if tokens != 0:
            await self._storage.save(bucket)
        return reservation

    def _time_for_tokens(self, tokens: int) -> float:
        return -(-tokens // self._amount) * self._cycle

    def _rate_limit(
        self,
        remaining: int,
        left: int,
        now: float,
        *,
        retry_after: float,
        accepted: bool,
    ) -> RateLimit:
        reset_at = now + self._time_for_tokens(max(0, self._max_burst - left))
        return RateLimit(
            remaining,
            instant(retry_after),
            accepted=accepted,
            limit=self._max_burst,
            reset_at=instant(reset_at),
            clock=self._clock,
        )
