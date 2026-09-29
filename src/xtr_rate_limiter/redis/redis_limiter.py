"""A limiter counting on a Redis server, one atomic script per hit."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from typing_extensions import override

from xtr_rate_limiter._time import instant
from xtr_rate_limiter.exception import InvalidArgumentError, MaxWaitDurationExceededError
from xtr_rate_limiter.limiter_interface import LimiterInterface
from xtr_rate_limiter.rate_limit import RateLimit
from xtr_rate_limiter.reservation import Reservation

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import datetime

    from xtr_clock import ClockInterface

    from ._script_runner import ScriptRunner

__all__ = ["RedisLimiter"]


@final
class RedisLimiter(LimiterInterface):
    """Counts the hits of one key on a Redis server.

    Each :meth:`reserve` is one script the server runs whole: it reads the
    state, decides, and writes the state back, so every process counting on
    the server shares the limit exactly, without a lock. The server's clock
    decides, so the processes' clocks need not agree.

    A server that cannot be reached raises
    :class:`~xtr_rate_limiter.exception.RateLimiterStorageError` rather than
    guessing: whether to let a hit through then is the caller's call.
    """

    __slots__ = ("_arguments", "_client_time", "_clock", "_key", "_limit", "_runner", "_script")

    def __init__(  # noqa: PLR0913 — every option past the key is keyword-only.
        self,
        key: str,
        *,
        script: str,
        arguments: Callable[[datetime], Sequence[str | int | float]],
        limit: int,
        runner: ScriptRunner,
        clock: ClockInterface,
        client_time: bool = False,
    ) -> None:
        """Count on ``key`` with ``script``, passed what ``arguments`` returns each time.

        Args:
            key: The Redis key the state is kept under.
            script: The policy's script.
            arguments: Builds the policy's arguments, after the time and the
                tokens, from the current instant.
            limit: The most tokens the limiter holds.
            runner: Runs the script on the server.
            clock: What instants are reported against.
            client_time: Count by this process's clock rather than the
                server's — for a calendar worked out here, which the script
                must see the same instant as.
        """
        self._key = key
        self._script = script
        self._arguments = arguments
        self._limit = limit
        self._runner = runner
        self._clock = clock
        self._client_time = client_time

    @override
    async def reserve(self, tokens: int = 1, max_time: float | None = None) -> Reservation:
        """Book ``tokens`` for the moment they become available."""
        if tokens < 0:
            raise InvalidArgumentError(f"Cannot reserve a negative number of tokens ({tokens}).")
        if tokens > self._limit:
            raise InvalidArgumentError(
                f"Cannot reserve more tokens ({tokens}) than the size of the rate limiter "
                f"({self._limit}).",
            )
        moment = self._clock.now()
        now = moment.timestamp()
        answer = await self._runner.run(
            self._script,
            self._key,
            [tokens, "" if max_time is None else repr(float(max_time)), *self._arguments(moment)],
            now=now if self._client_time else None,
        )
        accepted, exceeded, remaining, retry_after, time_to_act, reset_at = answer
        limit = RateLimit(
            int(float(_text(remaining))),
            instant(now + float(_text(retry_after))),
            int(_text(accepted)) == 1,
            self._limit,
            instant(now + float(_text(reset_at))),
            clock=self._clock,
        )
        wait = float(_text(time_to_act))
        if int(_text(exceeded)) == 1 and max_time is not None:
            raise MaxWaitDurationExceededError(wait, max_time, limit)
        return Reservation(now + wait, limit, clock=self._clock)

    @override
    async def consume(self, tokens: int = 1) -> RateLimit:
        """Spend ``tokens`` now if they are available; spend nothing otherwise."""
        try:
            return (await self.reserve(tokens, 0)).rate_limit
        except MaxWaitDurationExceededError as error:
            return error.rate_limit

    @override
    async def reset(self) -> None:
        """Forget every hit counted for this key."""
        await self._runner.delete(self._key)


def _text(value: object) -> str:
    """Read a script's answer, which the client hands back as bytes or text."""
    return value.decode() if isinstance(value, bytes) else str(value)
