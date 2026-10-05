<div align="center">

# xtr-rate-limiter

**Limits on how often anything may happen — calls, jobs, logins — by fixed window, sliding window or token bucket, kept in memory, in a cache or atomically in Redis.**

<img alt="python 3.11+" src="https://img.shields.io/badge/python-%E2%89%A5%203.11-3776AB?logo=python&logoColor=white">
<img alt="typed" src="https://img.shields.io/badge/typed-ty%20%2B%20basedpyright-1f6feb">
<img alt="license MIT" src="https://img.shields.io/badge/license-MIT-blue">

</div>

---

## Why?

A limit is not a web concern. A worker calling a paid API, a job retrying a flaky upstream, a
login form, a message consumer draining a queue — each needs to know whether it may go ahead
now, or when it may. This library answers that for any key, from any code, without a web
framework in sight.

- 🪣 **Three policies.** A fixed window, a sliding window that smooths bursts at window edges,
  and a token bucket that allows bursts then a steady rate — plus no limit at all.
- ⏳ **Decide now, or book ahead.** `consume()` grants tokens or refuses; `reserve()` books
  them for the moment they come free and says when that is.
- 🧱 **Anywhere the state fits.** In this process, in a cache pool shared by every process, or
  on a Redis server that counts each hit in one atomic script — no lock needed.
- 🧩 **Combined limits.** 10 a minute *and* 1 000 a day, as one limiter.

## Install

```sh
uv add xtr-rate-limiter                  # policies, in-memory storage
uv add "xtr-rate-limiter[redis]"         # + atomic counting on a Redis server
uv add "xtr-rate-limiter[cache]"         # + state in a cache pool
uv add "xtr-rate-limiter[lock]"          # + locks shared between processes
uv add "xtr-rate-limiter[di]"            # + the bundle
```

## Quick start

A factory is one configured limit; it hands out a limiter per key:

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

`consume()` answers with a `RateLimit`:

| Member | Meaning |
|---|---|
| `is_accepted()` | the tokens were granted |
| `remaining_tokens` | tokens left |
| `retry_after` | when the tokens asked for become available |
| `reset_at` | when the limiter holds every token again (`None` for no limit) |
| `limit` | tokens held when full |
| `ensure_accepted()` | return the limit, or raise `RateLimitExceededError` |
| `await wait()` | wait until `retry_after` |

Consuming `0` tokens reports the limit as it stands and spends nothing.

### Waiting instead of refusing

`reserve()` books the tokens for when they come free. From then on they count as spent, so
callers are served in the order they reserved:

```python
reservation = await limiter.reserve(tokens=1, max_time=5)
await reservation.wait()
await call_the_api()
```

A wait longer than `max_time` raises `MaxWaitDurationExceededError` and books nothing.

## Policies

`LimiterConfig`'s `policy` picks which of its other fields apply:

```python
LimiterConfig("fixed_window", limit=5, interval="15 minutes")
LimiterConfig("fixed_window", limit=1000, interval="1 month", anchor_at="2026-01-01")
LimiterConfig("sliding_window", limit=100, interval="1 minute")
LimiterConfig("token_bucket", limit=10, rate=Rate("1 minute", amount=2))
LimiterConfig("no_limit")
LimiterConfig("compound", limiters=["per_minute", "per_day"])
```

- **`fixed_window`** — at most `limit` hits per window of `interval`. A window opens on the
  first hit; with `anchor_at` (an interval of a month or more) windows follow a calendar
  instead — the first of each month, whenever hits arrive. Cheap, but a burst at the end of
  one window and another at the start of the next go through together.
- **`sliding_window`** — at most `limit` hits in any span of `interval`, estimated from the
  current window and a fading share of the last one. Smooths the edge burst out.
- **`token_bucket`** — a bucket of `limit` tokens refilled by `rate`: an idle caller can burst,
  a busy one settles to the rate.
- **`no_limit`** — accepts everything; for a limit turned off in one environment.
- **`compound`** — every one of `limiters` applies to each hit (configured by the bundle; in
  code, `CompoundRateLimiterFactory`). The answer is the first refusal, or the limit closest to
  running out. Limits consulted before a refusal keep their spend, and a compound limiter
  cannot `reserve()`.

Intervals are written `"30 seconds"`, `"1 hour 30 minutes"`, `"2 weeks"`, `"1 month"` — or as a
`timedelta`. A reservation beyond a window's size is a debt the following windows pay, so no
token is ever handed out twice.

## Where the state lives

| Storage | Shared by | Guarded by |
|---|---|---|
| `InMemoryStorage()` | this process | a lock within the process |
| `CacheStorage(pool)` | every process reaching the pool | a lock from a `LockFactory` |
| `RedisRateLimiterFactory(...)` | every process reaching the server | one atomic script per hit |

A storage limiter reads its state, decides, and writes it back under a lock on the key — held
within the process when no lock factory is given, which already matters in one process: a task
can be switched away from between the read and the write. Pass an `xtr-lock` `LockFactory` to
share the lock between processes:

```python
factory = RateLimiterFactory("api", config, CacheStorage(pool), LockFactory(RedisStore(redis)))
```

A cache pool never fails loudly: a pool whose backend is down reads as empty, so a limiter on
it lets every hit through until the backend is back. Use Redis for limits that must hold then.

### Redis

`RedisRateLimiterFactory` keeps each limiter's state in one hash and changes it in one script
the server runs whole — no lock, one round trip, and the server's own clock, so the processes'
clocks need not agree:

```python
from redis.asyncio import Redis
from xtr_rate_limiter.redis import RedisRateLimiterFactory

factory = RedisRateLimiterFactory(
    "login",
    LimiterConfig("fixed_window", limit=5, interval="15 minutes"),
    Redis.from_url("redis://localhost:6379"),
)
```

Keys are `"<prefix><id>-<key>"` (`prefix="rate_limiter:"`), each expiring once it no longer
matters. A server that cannot be reached raises `RateLimiterStorageError` rather than guessing:
whether to let a hit through then is the caller's call. A server refusing to read its clock in a
script is sent this process's instead; a calendar-anchored window always counts by this
process's clock, since the calendar is worked out here.

### Building limits in code

For limits decided at runtime — per tenant, per plan:

```python
builder = RateLimiterBuilder(InMemoryStorage())
factory = builder.token_bucket(f"tenant-{tenant.id}", limit=tenant.burst, interval="1 second")
```

`sliding_window`, `fixed_window`, `token_bucket`, `compound` and `noop` build a factory each.

## Reporting a refusal

A denied hit is not a rejection by itself — a caller may wait, retry or carry on — so limiters
dispatch nothing. Code that turns a hit away can dispatch `RateLimitExceededEvent(rate_limit,
limiter_name, key)` through its event dispatcher.

## Use in an application

Everything adding this package to an application on
[xtr-dependency-injection](../xtr-dependency-injection) takes — and, read backwards, what
removing it undoes.

- **Install** — `uv add "xtr-rate-limiter[di]"`; add `cache` and xtr-cache for state shared
  through a cache pool, `lock` and xtr-lock for a lock shared between processes, `redis` to
  count on a Redis server.
- **Recipe** — `uv run xtr-recipes recipes:sync` does the *Activate* step below: it lists
  `RateLimiterBundle`. There is no config file, environment or ignore line to write; it prints the
  step to name your limiters in `config/rate_limiter.py`, which a recipe cannot make for you.
- **Activate** — `RateLimiterBundle: {"all": True}` in `BUNDLES` in `<app>/bundles.py`,
  imported from `xtr_rate_limiter.bundle`.
- **Brings along** — the cache bundle when xtr-cache is installed, and the lock bundle when
  xtr-lock is.
- **Configure** — optional: with no configuration there are no limiters. Limiters go in
  `<app>/config/rate_limiter.py`, a `@configure` function returning `RateLimiterConfig` — see
  [Kernel / bundle](#kernel--bundle).
- **Environment** — nothing required. A storage given as `env(...)` must be set when the
  application boots: booting checks every limiter.
- **Ignore** — nothing beyond what the cache and lock bundles write under `var/`.
- **Remove** — drop the `BUNDLES` entry, delete `<app>/config/rate_limiter.py`, then
  `uv remove xtr-rate-limiter`.
- **Check** — `debug:bundles` shows `rate_limiter` as `listed` and `active`.

## Kernel / bundle

```python
# app/bundles.py
from xtr_rate_limiter.bundle import RateLimiterBundle

BUNDLES = {RateLimiterBundle: {"all": True}}
```

```python
# app/config/rate_limiter.py
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

Every limiter is a `RateLimiterFactoryInterface` qualified by its name:

```python
from typing import Annotated

from xtr_dependency_injection import Target, as_service

from xtr_rate_limiter import RateLimiterFactoryInterface


@as_service
class LoginThrottle:
    def __init__(self, limiter: Annotated[RateLimiterFactoryInterface, Target("login")]) -> None:
        self._limiter = limiter
```

`RateLimiterConfig`:

| Field | Default | What it sets |
|---|---|---|
| `limiters` | `{}` | every limiter, by name |
| `builder` | `BuilderConfig()` | where the `RateLimiterBuilder` service keeps its state |
| `redis_prefix` | `"rate_limiter:"` | what every key counted in Redis starts with |

Each `LimiterConfig` also says where its state lives:

| Field | Default | What it sets |
|---|---|---|
| `storage` | `"cache"` | `"cache"`, `"in-memory"`, a Redis DSN, or a `Reference` to a `StorageInterface` or a Redis client — also `env(...)` |
| `cache_pool` | `"rate_limiter"` | the pool a `"cache"` storage uses; the bundle adds it to the cache, on the application's adapter under a namespace of its own |
| `lock` | `"auto"` | the lock bundle's default factory when active, else within the process; a lock resource's name; or `None` for within the process only |

The bundle registers a factory per limiter and the `RateLimiterBuilder`, and its zero-config
path registers no limiter and touches no I/O. Boot checks every storage — a cache pool that
exists, a Redis DSN, a registered reference — so a mistake fails at startup rather than on the
first hit. A connection the bundle opened from a DSN is closed with the container.

## Errors

Everything this library raises derives from `RateLimiterError`, and carries what went wrong as
typed attributes rather than only a message.

| Error | Raised when |
|---|---|
| `InvalidArgumentError` | a configuration or call cannot be used — also a `ValueError` |
| `InvalidIntervalError` | an interval cannot be read |
| `MaxWaitDurationExceededError` | a reservation would wait longer than `max_time` |
| `RateLimitExceededError` | `ensure_accepted()` on a refused limit |
| `ReserveNotSupportedError` | `reserve()` on a compound limiter |
| `RateLimiterStorageError` | the Redis server failed or could not be reached |

## Development

Developed in the [python-xtr](https://github.com/xterr/python-xtr) monorepo, under
`packages/xtr-rate-limiter`; run the commands below from there. The `python-xtr-rate-limiter`
repository is a read-only copy, so send issues and pull requests to the monorepo.

```sh
uv sync --all-extras
uv run ruff check && uv run ruff format --check && uv run basedpyright && uv run ty check && uv run pytest
```

The Redis scripts run in process, on a fake server; no Redis is needed.

## License

MIT — see [LICENSE](LICENSE).
