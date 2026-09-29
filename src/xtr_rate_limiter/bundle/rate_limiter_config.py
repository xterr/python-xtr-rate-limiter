"""Configuration for :class:`~xtr_rate_limiter.bundle.rate_limiter_bundle.RateLimiterBundle`."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from xtr_dependency_injection import Reference

from xtr_rate_limiter.exception import InvalidArgumentError
from xtr_rate_limiter.limiter_config import LimiterConfig
from xtr_rate_limiter.redis.redis_rate_limiter_factory import DEFAULT_PREFIX

from .builder_config import BuilderConfig

__all__ = ["RateLimiterConfig"]


def _no_limiters() -> dict[str, LimiterConfig]:
    return {}


@dataclass(frozen=True, slots=True)
class RateLimiterConfig:
    """Which limiters exist, by name.

    Every limiter becomes a
    :class:`~xtr_rate_limiter.rate_limiter_factory_interface.RateLimiterFactoryInterface`
    qualified by its name. With no configuration there are none.

    ```python
    RateLimiterConfig(
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

    Attributes:
        limiters: Every limiter, by name.
        builder: Where the limiters the
            :class:`~xtr_rate_limiter.rate_limiter_builder.RateLimiterBuilder`
            service builds keep their state.
        redis_prefix: What every key a limiter counting in Redis writes
            starts with; give two applications sharing a server different
            ones.
    """

    limiters: Mapping[str, LimiterConfig] = field(default_factory=_no_limiters)
    builder: BuilderConfig = field(default_factory=BuilderConfig)
    redis_prefix: str = DEFAULT_PREFIX

    def __post_init__(self) -> None:
        """Refuse a limiter not named, not a ``LimiterConfig``, or combining a compound one.

        Raises:
            InvalidArgumentError: When the configuration cannot be used.
        """
        for name, limiter in self.limiters.items():
            if not isinstance(name, str) or name == "":  # pyright: ignore[reportUnnecessaryIsInstance] -- configs are written by hand; the annotation is not enforced
                raise InvalidArgumentError(f"A rate limiter needs a non-empty name, got {name!r}.")
            if not isinstance(limiter, LimiterConfig):  # pyright: ignore[reportUnnecessaryIsInstance] -- as above
                raise InvalidArgumentError(
                    f'The "{name}" rate limiter must be a LimiterConfig, got {limiter!r}.',
                )
            if not isinstance(limiter.storage, (str, Reference)):  # pyright: ignore[reportUnnecessaryIsInstance] -- as above
                raise InvalidArgumentError(
                    f'The "{name}" rate limiter\'s storage must be a string or a Reference, '
                    f"got {limiter.storage!r}.",
                )
            if limiter.policy == "compound":
                self._check_compound(name, limiter)

    def _check_compound(self, name: str, limiter: LimiterConfig) -> None:
        for combined in limiter.limiters:
            target = self.limiters.get(combined)
            if target is None:
                raise InvalidArgumentError(
                    f'The "{name}" compound rate limiter combines "{combined}", '
                    f"which is not a configured rate limiter.",
                )
            if target.policy == "compound":
                raise InvalidArgumentError(
                    f'The "{name}" compound rate limiter combines "{combined}", '
                    f"which is a compound rate limiter itself.",
                )
