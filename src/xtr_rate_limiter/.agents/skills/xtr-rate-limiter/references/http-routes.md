# Limiting HTTP routes

With `xtr-http-kernel[rate-limiter]`, `RateLimited` holds a route, a router or the whole
application to a limiter the rate limiter bundle configured. It is a dependency, so it runs
after routing and before the endpoint, in the framework's order: the application's limits, the
routers', then the route's.

```python
from fastapi import APIRouter, FastAPI, Request

from xtr_http_kernel.rate_limiter import RateLimited

app = FastAPI(dependencies=[RateLimited("global")])  # every route


@app.get("/books")
@RateLimited("api", expose_headers=True)  # below the route decorator
async def list_books() -> list[Book]: ...


def by_username(request: Request) -> str:
    return request.headers.get("x-username", "anonymous")


@app.post("/login", dependencies=[RateLimited("login", key=by_username, methods="post")])
async def login() -> None: ...


reports = RateLimited("reports")(APIRouter(prefix="/reports"))  # before its routes
app.include_router(admin, dependencies=[RateLimited("admin")])  # or when included
```

`RateLimited(limiter, *, key=None, tokens=1, methods=(), expose_headers=False)`:

| Argument | Is |
| --- | --- |
| `limiter` | the name the limiter is configured under |
| `key` | a string, or a function of the request — awaited when it returns an awaitable. By default the client's address, the method and the route's path template (`/books/{isbn}`) |
| `tokens` | the tokens one request consumes |
| `methods` | the methods limited; every one when empty, and `GET` also limits `HEAD` |
| `expose_headers` | report this limit in `X-RateLimit-*` |

## Rules worth remembering

- As a decorator it must sit **below** the route decorator, which reads the endpoint when the
  route is declared.
- A router must be limited **before** routes are added: each route copies its router's
  dependencies.
- Behind a proxy the default key is the proxy's address unless the server trusts its forwarded
  headers (uvicorn's `--forwarded-allow-ips`).
- The published schema is untouched: the limit never appears as a parameter.

## A refusal

Answered `429 Too Many Requests` with `Retry-After`, raised as `TooManyRequestsError` — the
framework's own HTTP exception, so an exception handler registered for it reshapes the body. A
`RateLimitExceededEvent` naming the limiter and the key is dispatched first, and limits
consulted before the refusal keep their spend.

With `expose_headers=True` the response carries `X-RateLimit-Limit`, `X-RateLimit-Remaining` and
`X-RateLimit-Reset`, in calls rather than tokens, for the limit closest to refusing among those
exposing theirs; a refusing limit always speaks. The response is made private, so a shared cache
never serves one caller's count to another.

A limiter the application did not configure fails the request with `UnknownRateLimiterError`,
naming the ones it did.

## Limiting by hand

To throttle only on failure — a wrong password, say — inject the limiter by name and consume
where the decision belongs:

```python
from typing import Annotated

from xtr_dependency_injection import Target
from xtr_rate_limiter import RateLimiterFactoryInterface


@app.post("/login")
async def login(
    limiter: Annotated[RateLimiterFactoryInterface, Target("login")],
) -> None:
    limit = limiter.create(username)
    if not (await limit.consume(0)).is_accepted():  # peek, spending nothing
        raise TooManyAttempts
    ...
```
