from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError

from xtr_rate_limiter import RateLimiterStorageError
from xtr_rate_limiter.redis._script_runner import ScriptRunner

if TYPE_CHECKING:
    from fakeredis import FakeAsyncRedis
    from xtr_clock import MockClock

pytestmark = pytest.mark.anyio

_ECHO_TIME = "return ARGV[1]"


async def test_a_server_that_forgot_the_script_is_sent_it_again(
    redis_client: FakeAsyncRedis, clock: MockClock
) -> None:
    runner = ScriptRunner(redis_client, clock)
    _ = await runner.run(_ECHO_TIME, "k", [])

    _ = await redis_client.script_flush()

    assert await runner.run(_ECHO_TIME, "k", []) == b""


async def test_the_time_is_left_to_the_server_unless_given(
    redis_client: FakeAsyncRedis, clock: MockClock
) -> None:
    runner = ScriptRunner(redis_client, clock)

    assert await runner.run(_ECHO_TIME, "k", []) == b""
    assert await runner.run(_ECHO_TIME, "k", [], now=12.5) == b"12.5"


async def test_without_server_time_our_clock_is_sent(
    redis_client: FakeAsyncRedis, clock: MockClock
) -> None:
    runner = ScriptRunner(redis_client, clock, server_time=False)

    answer = await runner.run(_ECHO_TIME, "k", [])

    assert answer == repr(clock.now().timestamp()).encode()


async def test_a_server_refusing_its_clock_in_a_script_is_sent_ours_from_then_on(
    redis_client: FakeAsyncRedis, clock: MockClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    evalsha = redis_client.evalsha
    times: list[object] = []

    async def refusing(sha: str, numkeys: int, *keys_and_args: object) -> object:
        times.append(keys_and_args[1])
        if keys_and_args[1] == "":
            message = "Write commands not allowed after non deterministic commands"
            raise ResponseError(message)
        arguments = cast("tuple[str, ...]", keys_and_args)
        answer: object = await evalsha(sha, numkeys, *arguments)  # pyright: ignore[reportAny]
        return answer

    monkeypatch.setattr(redis_client, "evalsha", refusing)
    runner = ScriptRunner(redis_client, clock)

    _ = await runner.run(_ECHO_TIME, "k", [])
    _ = await runner.run(_ECHO_TIME, "k", [])

    assert times[0] == ""
    assert set(times[1:]) == {repr(clock.now().timestamp())}


@pytest.mark.parametrize(
    "error", [ResponseError("ERR something else"), RedisConnectionError("down")]
)
async def test_a_failing_server_raises_rather_than_guessing(
    redis_client: FakeAsyncRedis,
    clock: MockClock,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    async def failing(*_: object) -> object:
        raise error

    monkeypatch.setattr(redis_client, "evalsha", failing)
    monkeypatch.setattr(redis_client, "delete", failing)
    runner = ScriptRunner(redis_client, clock)

    with pytest.raises(RateLimiterStorageError):
        _ = await runner.run(_ECHO_TIME, "k", [])
    with pytest.raises(RateLimiterStorageError):
        await runner.delete("k")


async def test_a_failing_server_raises_on_our_clock_too(
    redis_client: FakeAsyncRedis, clock: MockClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing(*_: object) -> object:
        message = "down"
        raise RedisConnectionError(message)

    monkeypatch.setattr(redis_client, "evalsha", failing)

    with pytest.raises(RateLimiterStorageError):
        _ = await ScriptRunner(redis_client, clock, server_time=False).run(_ECHO_TIME, "k", [])
