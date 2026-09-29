"""Several limits on one hit: accepted only when every one of them accepts it."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from typing_extensions import override

from .exception import InvalidArgumentError, ReserveNotSupportedError
from .limiter_interface import LimiterInterface

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .rate_limit import RateLimit
    from .reservation import Reservation

__all__ = ["CompoundLimiter"]


@final
class CompoundLimiter(LimiterInterface):
    """Consumes from each limiter in turn, stopping at the first that refuses.

    Say 10 hits a minute and 1 000 a day: both apply to every hit. The answer
    is the refusal when one refuses, and otherwise the limit closest to
    running out.

    The limiters consulted before a refusal have spent their tokens; they are
    not given back. Only :meth:`consume` is offered — reserving on several
    limiters would book tokens on some while another refuses.
    """

    __slots__ = ("_limiters",)

    def __init__(self, limiters: Sequence[LimiterInterface]) -> None:
        """Combine ``limiters``, consulted in order.

        Raises:
            InvalidArgumentError: When ``limiters`` is empty.
        """
        if not limiters:
            raise InvalidArgumentError("A compound limiter needs at least one limiter.")
        self._limiters = tuple(limiters)

    @override
    async def reserve(self, tokens: int = 1, max_time: float | None = None) -> Reservation:
        """Refuse: a compound limiter cannot reserve.

        Raises:
            ReserveNotSupportedError: Always.
        """
        raise ReserveNotSupportedError(type(self).__name__)

    @override
    async def consume(self, tokens: int = 1) -> RateLimit:
        """Consume ``tokens`` from every limiter until one refuses."""
        accepted: list[RateLimit] = []
        for limiter in self._limiters:
            limit = await limiter.consume(tokens)
            if not limit.is_accepted():
                return limit
            accepted.append(limit)
        return min(accepted, key=lambda limit: limit.remaining_tokens)

    @override
    async def reset(self) -> None:
        """Reset every limiter."""
        for limiter in self._limiters:
            await limiter.reset()
