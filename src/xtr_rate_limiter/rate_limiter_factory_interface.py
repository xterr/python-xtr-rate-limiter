"""What hands out a limiter per key."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .limiter_interface import LimiterInterface

__all__ = ["RateLimiterFactoryInterface"]


@runtime_checkable
class RateLimiterFactoryInterface(Protocol):
    """One configured limit, handing out a limiter for each key it is asked about.

    ```python
    limiter = factory.create(f"user-{user.id}")
    (await limiter.consume()).ensure_accepted()
    ```
    """

    def create(self, key: str | None = None) -> LimiterInterface:
        """Return the limiter counting the hits of ``key``.

        Limiters for the same key share their count, whichever factory call
        made them. ``None`` is one key like any other: a limit shared by
        every caller.
        """
        ...
