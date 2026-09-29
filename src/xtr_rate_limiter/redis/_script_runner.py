"""Running a limiter's script on the server, by the server's clock when it lets us."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Final, Protocol, cast, final

from xtr_rate_limiter.exception import RateLimiterStorageError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Sequence

    from redis.asyncio import Redis
    from xtr_clock import ClockInterface

__all__ = ["ScriptRunner"]

_TIME_REFUSALS: Final = (
    "commands not allowed after non deterministic",
    "is not allowed from script",
)
"""What a server says when a script may not read its clock and then write."""


class _ScriptingClient(Protocol):
    """The calls a runner makes, typed as the asyncio client answers them."""

    def evalsha(
        self, sha: str, numkeys: int, /, *keys_and_args: str | float
    ) -> Awaitable[object]: ...

    def script_load(self, script: str, /) -> Awaitable[str]: ...

    def delete(self, *names: str) -> Awaitable[object]: ...


@final
class ScriptRunner:
    """Runs scripts by their digest on one client, loading them when the server forgot them.

    Scripts read the server's own clock, so every process counting on it
    agrees on the time. A server that refuses a script reading its clock and
    then writing — one not replicating script effects — is sent this process's
    clock instead, from the first refusal on.
    """

    __slots__ = ("_client", "_clock", "_server_time")

    def __init__(self, client: Redis, clock: ClockInterface, *, server_time: bool = True) -> None:
        """Run scripts on ``client``; send ``clock``'s time when the server's cannot be read."""
        self._client = cast("_ScriptingClient", client)
        self._clock = clock
        self._server_time = server_time

    async def run(
        self, script: str, key: str, args: Sequence[str | int | float], *, now: float | None = None
    ) -> list[object]:
        """Run ``script`` on ``key`` with ``args``, the time first.

        Args:
            script: The script to run.
            key: The one key it touches.
            args: Its arguments after the time.
            now: The time to send, even when the server's could be read;
                the server's, or this process's clock, when ``None``.

        Raises:
            RateLimiterStorageError: When the server fails, or cannot be
                reached.
        """
        from redis.exceptions import (  # noqa: PLC0415 — the redis extra is optional.
            RedisError,
            ResponseError,
        )

        if self._server_time and now is None:
            try:
                return await self._evaluate(script, key, ["", *args])
            except ResponseError as error:
                if not any(refusal in str(error) for refusal in _TIME_REFUSALS):
                    raise RateLimiterStorageError(str(error)) from error
                self._server_time = False
            except RedisError as error:
                raise RateLimiterStorageError(str(error)) from error
        try:
            sent = now if now is not None else self._clock.now().timestamp()
            return await self._evaluate(script, key, [repr(sent), *args])
        except RedisError as error:
            raise RateLimiterStorageError(str(error)) from error

    async def delete(self, key: str) -> None:
        """Delete ``key``.

        Raises:
            RateLimiterStorageError: When the server fails, or cannot be
                reached.
        """
        from redis.exceptions import RedisError  # noqa: PLC0415 — the redis extra is optional.

        try:
            _ = await self._client.delete(key)
        except RedisError as error:
            raise RateLimiterStorageError(str(error)) from error

    async def _evaluate(
        self, script: str, key: str, args: Sequence[str | int | float]
    ) -> list[object]:
        from redis.exceptions import NoScriptError  # noqa: PLC0415 — the redis extra is optional.

        digest = hashlib.sha1(script.encode(), usedforsecurity=False).hexdigest()
        try:
            answer = await self._client.evalsha(digest, 1, key, *args)
        except NoScriptError:
            _ = await self._client.script_load(script)
            answer = await self._client.evalsha(digest, 1, key, *args)
        return cast("list[object]", answer)
