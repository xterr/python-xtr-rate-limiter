---
name: xtr-rate-limiter
description: How to limit how often anything may happen with xtr-rate-limiter — fixed window, sliding window and token bucket limits, consumed or reserved, kept in memory, in a cache pool or atomically in Redis. Use when code must throttle calls, logins, uploads, jobs, retries or outbound API usage; when you need "N per minute", a burst allowance, a 429 with Retry-After, X-RateLimit headers, or a worker that waits for its turn; also when adding RateLimiterBundle to an application, configuring named limiters, or limiting a route with RateLimited on xtr-http-kernel.
---

# xtr-rate-limiter

A limit is not a web concern. A factory is one configured limit; it hands out a limiter per
key — a user, an address, an account — and the limiter answers whether a hit may go ahead now,
or when it may. Every call that touches a limiter is awaited.

## Quick reference

- `factory.create(key)` → a `LimiterInterface`. `await limiter.consume(tokens=1)` → a `RateLimit`.
- `consume(0)` reports the limit as it stands and spends nothing. Use it to peek.
- `await limiter.reserve(tokens, max_time)` books tokens for when they come free;
  `await reservation.wait()` then waits. `await limiter.reset()` forgets the key's count.
- Policies: `"fixed_window"`, `"sliding_window"`, `"token_bucket"`, `"no_limit"`, `"compound"`.
- Storage: `InMemoryStorage()` (this process), `CacheStorage(pool)` (every process on the pool),
  `RedisRateLimiterFactory(...)` (one atomic script per hit, no lock).
- In an application: activate `RateLimiterBundle`, name limiters in `RateLimiterConfig`, inject
  `Annotated[RateLimiterFactoryInterface, Target("<name>")]`.
- Limiters dispatch nothing. Code that turns a hit away dispatches `RateLimitExceededEvent`.

## Decide now

```python
from xtr_rate_limiter import InMemoryStorage, LimiterConfig, RateLimiterFactory

factory = RateLimiterFactory(
    "api",
    LimiterConfig("sliding_window", limit=100, interval="1 minute"),
    InMemoryStorage(),
)

limit = await factory.create(client_ip).consume()
if not limit.is_accepted():
    raise TooBusy(retry_after=limit.retry_after)
```

A `RateLimit` carries the whole answer:

| Member | Is |
| --- | --- |
| `is_accepted()` | whether the tokens were granted |
| `remaining_tokens` | tokens left |
| `retry_after` | a `datetime`: when the tokens asked for become available |
| `reset_at` | a `datetime`, or `None` for no limit: when every token is held again |
| `limit` | tokens held when full |
| `ensure_accepted()` | the limit itself, or `RateLimitExceededError` |
| `await wait()` | waits until `retry_after` |

## Wait instead of refusing

`reserve()` books the tokens, so callers are served in the order they reserved. Right for a
worker calling a paid API; wrong for a request a caller is holding open.

```python
reservation = await limiter.reserve(tokens=1, max_time=5)
await reservation.wait()  # returns at once when the tokens are already free
await call_the_api()
```

- `reservation.time_to_act` is a Unix timestamp; `reservation.wait_duration()` is a **method**
  returning the seconds left, zero once it passed.
- `reservation.rate_limit` is the limit as the booking left it — not accepted, because the
  tokens are spent ahead of time.
- A wait longer than `max_time` raises `MaxWaitDurationExceededError` and books nothing.
- A compound limiter cannot reserve: `ReserveNotSupportedError`.

## Pick a policy

```python
from xtr_rate_limiter import LimiterConfig, Rate

LimiterConfig("fixed_window", limit=5, interval="15 minutes")
LimiterConfig("fixed_window", limit=1000, interval="1 month", anchor_at="2026-01-01")
LimiterConfig("sliding_window", limit=100, interval="1 minute")
LimiterConfig("token_bucket", limit=10, rate=Rate("1 minute", amount=2))
LimiterConfig("no_limit")
LimiterConfig("compound", limiters=["api", "uploads"], keys={"global": "all"})
```

| Policy | Takes | Behaves |
| --- | --- | --- |
| `fixed_window` | `limit`, `interval`, optional `anchor_at` | cheapest; a burst either side of a window edge goes through together |
| `sliding_window` | `limit`, `interval` | at most `limit` in any span of `interval`; smooths the edge burst |
| `token_bucket` | `limit`, `rate` | an idle caller bursts up to `limit`, a busy one settles to the rate |
| `no_limit` | nothing | accepts everything; for a limit switched off in one environment |
| `compound` | `limiters`, optional `keys` | every named limiter applies to each hit |

- Intervals are written `"30 seconds"`, `"1 hour 30 minutes"`, `"2 weeks"`, `"1 month"`, or a
  `timedelta`. `Rate` also has `Rate.per_second(2)`, `per_minute`, `per_hour`, `per_day`,
  `per_month`, `per_year`.
- `anchor_at` needs an interval of at least a month; it makes windows follow a calendar instead
  of opening on the first hit.
- A field a policy does not take is refused with `InvalidArgumentError` when the config is
  built, not later.
- Compound answers with the first refusal, or the limit closest to running out. Limits consulted
  before a refusal keep their spend. In code it is `CompoundRateLimiterFactory`, not
  `RateLimiterFactory`:

```python
from xtr_rate_limiter import CompoundRateLimiterFactory

per_user = CompoundRateLimiterFactory(
    {"burst": burst_factory, "daily": daily_factory},
    keys={"daily": "everyone"},  # one shared daily count
)
```

## Choose where the state lives

| Storage | Shared by | Guarded by |
| --- | --- | --- |
| `InMemoryStorage()` | this process | a lock within the process |
| `CacheStorage(pool)` | every process reaching the pool | a lock from an `xtr-lock` `LockFactory` |
| `RedisRateLimiterFactory(...)` | every process reaching the server | one atomic script per hit |

A storage limiter reads, decides and writes back under a lock on the key. Without a lock factory
the lock is held within the process — which already matters in one process, since a task can be
switched away from between the read and the write. Share it between processes by passing one:

```python
from xtr_lock import LockFactory
from xtr_rate_limiter import CacheStorage, RateLimiterFactory

factory = RateLimiterFactory("api", config, CacheStorage(pool), LockFactory(store))
```

A cache pool whose backend is down reads as empty, so a limiter on it lets every hit through
until the backend is back. Use Redis for a limit that must hold then.

```python
from redis.asyncio import Redis
from xtr_rate_limiter.redis import RedisRateLimiterFactory

factory = RedisRateLimiterFactory(
    "login",
    LimiterConfig("fixed_window", limit=5, interval="15 minutes"),
    Redis.from_url("redis://localhost:6379"),
)
```

Keys are `"<prefix><id>-<key>"`, `prefix="rate_limiter:"`, each expiring once it no longer
matters. The server's own clock counts, so the processes' clocks need not agree; pass
`server_time=False` to count by the given `clock` instead. A server that cannot be reached
raises `RateLimiterStorageError` rather than guessing.

## Build a limit at runtime

For a limit that depends on the tenant or the plan rather than on configuration:

```python
from xtr_rate_limiter import InMemoryStorage, RateLimiterBuilder

builder = RateLimiterBuilder(InMemoryStorage())
factory = builder.token_bucket(f"tenant-{tenant.id}", limit=tenant.burst, interval="1 second")
```

`sliding_window(id, limit, interval)`, `fixed_window(id, limit, interval, anchor_at=None)`,
`token_bucket(id, limit, interval, amount=1)`, `compound(*factories)` and `noop()` each return a
`RateLimiterFactoryInterface`. The bundle registers a `RateLimiterBuilder` service.

## Limit an HTTP route

With `xtr-http-kernel[rate-limiter]`, one declaration holds a route, a router or the whole
application to a limiter the bundle configured:

```python
from xtr_http_kernel.rate_limiter import RateLimited


@app.get("/books")
@RateLimited("api", expose_headers=True)  # must sit below the route decorator
async def list_books() -> list[Book]: ...
```

A refusal is a `429` with `Retry-After`, raised as `TooManyRequestsError`. See
[references/http-routes.md](references/http-routes.md) for the key function, `methods`, the
`X-RateLimit-*` headers, limiting a router, and throttling by hand.

## Report a refusal

A denied hit is not a rejection by itself, so nothing is dispatched for you:

```python
from xtr_rate_limiter import RateLimitExceededEvent

await dispatcher.dispatch(RateLimitExceededEvent(limit, limiter_name="api", key=client_ip))
```

## Testing

Hand the factory `InMemoryStorage` and a frozen clock, and the test is about the limit rather
than spent waiting for it:

```python
import pytest
from xtr_clock import MockClock
from xtr_rate_limiter import InMemoryStorage, LimiterConfig, RateLimiterFactory


@pytest.mark.anyio
async def test_a_sixth_login_is_refused() -> None:
    clock = MockClock("2026-01-01 00:00:00")
    limiter = RateLimiterFactory(
        "login",
        LimiterConfig("fixed_window", limit=5, interval="15 minutes"),
        InMemoryStorage(clock),
        clock=clock,
    ).create("bob")

    for _ in range(5):
        assert (await limiter.consume()).is_accepted()

    assert not (await limiter.consume()).is_accepted()
    clock.sleep(900)  # the window passes instantly
    assert (await limiter.consume()).is_accepted()
```

- Give the same clock to the storage and the factory, or the state expires against one clock and
  is read against another.
- `await reservation.wait()` on a `MockClock` returns at once and moves the clock forward, so a
  waiting worker is testable.
- Against Redis, build the factory with `server_time=False` so a frozen clock decides.
- Code under test that must never be limited takes `RateLimiterBuilder(...).noop()`.

## Use in an application

1. **Install** — `uv add "xtr-rate-limiter[di]"`; add `cache` with xtr-cache for state in a cache
   pool, `lock` with xtr-lock for a lock shared between processes, `redis` to count on a server.
2. **Activate** — `RateLimiterBundle: {"all": True}` in `BUNDLES` in `<app>/bundles.py`
   (`from xtr_rate_limiter.bundle import RateLimiterBundle`).
3. **Brings along** — the cache bundle when xtr-cache is installed, the lock bundle when
   xtr-lock is.
4. **Configure** — optional, but with no configuration there are no limiters:

   ```python
   # <app>/config/rate_limiter.py
   from xtr_dependency_injection import configure, env
   from xtr_rate_limiter import LimiterConfig, Rate
   from xtr_rate_limiter.bundle import RateLimiterConfig


   @configure
   def rate_limiter() -> RateLimiterConfig:
       return RateLimiterConfig(
           limiters={
               "api": LimiterConfig("sliding_window", limit=100, interval="1 minute"),
               "login": LimiterConfig(
                   "fixed_window", limit=5, interval="15 minutes", storage=env("REDIS_DSN")
               ),
               "uploads": LimiterConfig("token_bucket", limit=10, rate=Rate("1 minute", amount=2)),
               "strict": LimiterConfig("compound", limiters=["api", "uploads"]),
           },
       )
   ```

   `RateLimiterConfig` also takes `builder` (a `BuilderConfig`, where the `RateLimiterBuilder`
   service keeps its state) and `redis_prefix` (`"rate_limiter:"`). Each `LimiterConfig` says
   where its own state lives: `storage` (`"cache"` by default, `"in-memory"`, a Redis DSN, a
   `Reference`, or `env(...)`), `cache_pool` (`"rate_limiter"`), and `lock` (`"auto"`, a lock
   resource's name, or `None` for within the process only).
5. **Environment** — nothing required; a `storage` given as `env(...)` must be set when the
   application boots, because booting checks every limiter.
6. **Use** — inject a limiter by the name it is configured under:

   ```python
   from typing import Annotated

   from xtr_dependency_injection import Target, as_service
   from xtr_rate_limiter import RateLimiterFactoryInterface


   @as_service
   class LoginThrottle:
       def __init__(self, limiter: Annotated[RateLimiterFactoryInterface, Target("login")]) -> None:
           self._limiter = limiter
   ```

7. **Check** — `debug:bundles` shows `rate_limiter` as `listed` and `active`.
8. **Remove** — drop the `BUNDLES` entry, delete `<app>/config/rate_limiter.py`, then
   `uv remove xtr-rate-limiter`.

## Errors

Everything derives from `RateLimiterError` and carries typed attributes:

| Error | Raised when | Carries |
| --- | --- | --- |
| `InvalidArgumentError` | a configuration or call cannot be used; also a `ValueError` | `.reason` |
| `InvalidIntervalError` | an interval cannot be read | `.interval`, `.reason` |
| `MaxWaitDurationExceededError` | a reservation would wait longer than `max_time` | `.wait_duration`, `.max_time`, `.rate_limit` |
| `RateLimitExceededError` | `ensure_accepted()` on a refused limit | `.rate_limit` |
| `ReserveNotSupportedError` | `reserve()` on a compound limiter | `.limiter` |
| `RateLimiterStorageError` | the Redis server failed or could not be reached | `.reason` |

## Do not

- Do not call `RateLimiterFactory` with a `"compound"` config — it raises; build a
  `CompoundRateLimiterFactory` from the factories instead.
- Do not read `reservation.wait_duration` as an attribute: it is a method.
- Do not `reserve()` where a caller is waiting on a response; refuse with a `429` instead.
- Do not rely on a cache-backed limit while its backend is down — it accepts everything. Count
  on Redis for a limit that must hold.
- Do not reach for a limiter's storage, state or `_`-prefixed internals; `consume(0)` reports
  the limit without spending anything.
- Do not build a limiter per hit when the factory can be injected once and asked for a limiter
  per key.
