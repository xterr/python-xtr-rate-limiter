"""One configured limit, counted atomically on a Redis server."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast, final

from typing_extensions import override
from xtr_clock import Clock

from xtr_rate_limiter.exception import InvalidArgumentError
from xtr_rate_limiter.policy.no_limiter import NoLimiter
from xtr_rate_limiter.rate_limiter_factory_interface import RateLimiterFactoryInterface

from ._script_runner import ScriptRunner
from ._scripts import ANCHORED_FIXED_WINDOW, FIXED_WINDOW, SLIDING_WINDOW, TOKEN_BUCKET
from .redis_limiter import RedisLimiter

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from redis.asyncio import Redis
    from xtr_clock import ClockInterface

    from xtr_rate_limiter._interval import Interval
    from xtr_rate_limiter.limiter_config import LimiterConfig
    from xtr_rate_limiter.limiter_interface import LimiterInterface

__all__ = ["DEFAULT_PREFIX", "RedisRateLimiterFactory"]

DEFAULT_PREFIX: Final = "rate_limiter:"
"""What every key a factory writes starts with."""


@final
class RedisRateLimiterFactory(RateLimiterFactoryInterface):
    """Hands out limiters counting on a Redis server, each hit one atomic script.

    The same policies as :class:`~xtr_rate_limiter.rate_limiter_factory.RateLimiterFactory`,
    with no storage and no lock: the server keeps the state and changes it
    whole, so every process reaching it shares each limit exactly. Each
    limiter's state is one hash under ``"<prefix><id>-<key>"``, expiring once
    it no longer matters.

    ```python
    factory = RedisRateLimiterFactory(
        "login",
        LimiterConfig("fixed_window", limit=5, interval="15 minutes"),
        Redis.from_url("redis://localhost:6379"),
    )
    limit = await factory.create(username).consume()
    ```

    The client is the caller's: the factory never closes it.
    """

    __slots__ = ("_anchor", "_clock", "_config", "_id", "_interval", "_prefix", "_runner")

    def __init__(  # noqa: PLR0913 — every option past the client is keyword-only.
        self,
        limiter_id: str,
        config: LimiterConfig,
        client: Redis,
        *,
        prefix: str = DEFAULT_PREFIX,
        clock: ClockInterface | None = None,
        server_time: bool = True,
    ) -> None:
        """Count as ``config`` says on ``client``, named ``limiter_id``.

        Args:
            limiter_id: The limit's name, part of every key.
            config: How to count; its storage and lock fields are ignored.
            client: The server to count on.
            prefix: What every key starts with.
            clock: What instants are reported against, and the time sent
                when the server's cannot be read; the clock in force when
                ``None``.
            server_time: Count by the server's clock, so every process
                agrees; ``False`` counts by ``clock``, as a test with a
                frozen clock needs.

        Raises:
            InvalidArgumentError: When ``config`` is a compound limiter.
        """
        if config.policy == "compound":
            raise InvalidArgumentError(
                "A compound rate limiter combines factories: build a CompoundRateLimiterFactory.",
            )
        self._id = limiter_id
        self._config = config
        self._prefix = prefix
        self._clock: ClockInterface = clock if clock is not None else Clock()
        self._runner = ScriptRunner(client, self._clock, server_time=server_time)
        # Read once: a factory hands out a limiter per request.
        self._interval = None if config.interval is None else config.parsed_interval()
        self._anchor = config.anchor()

    @override
    def create(self, key: str | None = None) -> LimiterInterface:
        """Return the limiter counting the hits of ``key``."""
        config = self._config
        limit = config.limit
        if config.policy == "no_limit" or limit is None:
            return NoLimiter(self._clock)

        redis_key = f"{self._prefix}{self._id}-{key or ''}"
        now = self._clock.now().timestamp()
        if config.rate is not None:
            arguments: Sequence[str | int | float] = (
                limit,
                repr(config.rate.cycle_from(now)),
                config.rate.amount,
            )
            return self._limiter(redis_key, TOKEN_BUCKET, arguments, limit)

        # Only windows are left, and a window's config always has an interval.
        interval = cast("Interval", self._interval)
        if config.policy == "sliding_window":
            arguments = (limit, repr(interval.seconds_from(now)))
            return self._limiter(redis_key, SLIDING_WINDOW, arguments, limit)

        anchor = self._anchor
        if anchor is None:
            arguments = (limit, repr(interval.seconds_from(now)))
            return self._limiter(redis_key, FIXED_WINDOW, arguments, limit)
        return RedisLimiter(
            redis_key,
            script=ANCHORED_FIXED_WINDOW,
            arguments=lambda moment: (limit, repr(_period_end(interval, anchor, moment))),
            limit=limit,
            runner=self._runner,
            clock=self._clock,
            client_time=True,
        )

    def _limiter(
        self, key: str, script: str, arguments: Sequence[str | int | float], limit: int
    ) -> RedisLimiter:
        return RedisLimiter(
            key,
            script=script,
            arguments=lambda _: arguments,
            limit=limit,
            runner=self._runner,
            clock=self._clock,
        )


def _period_end(interval: Interval, anchor: datetime, moment: datetime) -> float:
    """Return when the calendar period holding ``moment`` ends.

    Worked out here, by this process's clock, whose time the script is then
    sent too: a calendar is not something a script can read.
    """
    _, end = interval.period_around(anchor, moment)
    return end.timestamp()
