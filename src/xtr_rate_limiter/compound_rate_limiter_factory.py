"""Several configured limits, combined into one limiter per key."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from typing_extensions import override

from .compound_limiter import CompoundLimiter
from .exception import InvalidArgumentError
from .rate_limiter_factory_interface import RateLimiterFactoryInterface

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .limiter_interface import LimiterInterface

__all__ = ["CompoundRateLimiterFactory"]


@final
class CompoundRateLimiterFactory(RateLimiterFactoryInterface):
    """Hands out a :class:`~xtr_rate_limiter.compound_limiter.CompoundLimiter` per key.

    ```python
    per_user = CompoundRateLimiterFactory(
        {"burst": burst_factory, "daily": daily_factory, "global": global_factory},
        keys={"global": "everyone"},
    )
    ```
    """

    __slots__ = ("_factories", "_keys")

    def __init__(
        self,
        factories: Mapping[str, RateLimiterFactoryInterface],
        keys: Mapping[str, str] | None = None,
    ) -> None:
        """Combine ``factories``, consulted in order.

        Args:
            factories: The factories to combine, by name.
            keys: A key to use for some of them instead of the one
                :meth:`create` is given.

        Raises:
            InvalidArgumentError: When ``factories`` is empty, or ``keys``
                names a factory not combined.
        """
        if not factories:
            raise InvalidArgumentError("A compound rate limiter needs at least one factory.")
        chosen = dict(keys or {})
        unknown = sorted(set(chosen) - set(factories))
        if unknown:
            raise InvalidArgumentError(
                f'Unknown rate limiter(s) "{", ".join(unknown)}" in the keys of a compound '
                "rate limiter.",
            )
        self._factories = dict(factories)
        self._keys = chosen

    @override
    def create(self, key: str | None = None) -> LimiterInterface:
        """Return a limiter combining one limiter of every factory."""
        return CompoundLimiter(
            [factory.create(self._keys.get(name, key)) for name, factory in self._factories.items()]
        )
