"""How one named limiter counts, and where it keeps what it counted."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Literal, TypeAlias, get_args

from ._interval import Interval, IntervalLike
from .exception import InvalidArgumentError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from xtr_dependency_injection import Reference

    from .policy.rate import Rate

__all__ = [
    "AUTO_LOCK",
    "CACHE_STORAGE",
    "DEFAULT_CACHE_POOL",
    "IN_MEMORY_STORAGE",
    "LimiterConfig",
    "Policy",
]

Policy: TypeAlias = Literal[
    "fixed_window", "sliding_window", "token_bucket", "no_limit", "compound"
]
"""How a limiter counts hits."""

CACHE_STORAGE: Final = "cache"
"""Keep states in a cache pool: :attr:`LimiterConfig.cache_pool`."""

IN_MEMORY_STORAGE: Final = "in-memory"
"""Keep states in this process only."""

DEFAULT_CACHE_POOL: Final = "rate_limiter"
"""The pool states are kept in: the cache's application pool, under a namespace of its own."""

AUTO_LOCK: Final = "auto"
"""Lock through the lock bundle's default factory when active; within this process otherwise."""

_POLICIES: Final = frozenset(get_args(Policy))
_WINDOWS: Final = frozenset({"fixed_window", "sliding_window"})
_UNLIMITED: Final = frozenset({"no_limit", "compound"})


def _no_keys() -> dict[str, str]:
    return {}


@dataclass(frozen=True, slots=True)
class LimiterConfig:
    """Configuration for a single named limiter.

    ``policy`` decides which of the other fields apply:

    - ``"fixed_window"`` — at most ``limit`` hits per window of ``interval``,
      opening on the first hit, or following a calendar from ``anchor_at``;
    - ``"sliding_window"`` — at most ``limit`` hits in any span of
      ``interval``;
    - ``"token_bucket"`` — bursts of up to ``limit`` hits, refilled at
      ``rate``;
    - ``"no_limit"`` — every hit accepted, nothing kept;
    - ``"compound"`` — every one of ``limiters`` applies to each hit.

    ```python
    LimiterConfig("sliding_window", limit=100, interval="1 minute")
    LimiterConfig("token_bucket", limit=10, rate=Rate("1 minute", amount=2))
    LimiterConfig("fixed_window", limit=5, interval="15 minutes", storage=env("REDIS_DSN"))
    LimiterConfig("compound", limiters=["api", "uploads"])
    ```

    A factory reads how the limiter counts; the bundle also reads
    ``storage``, ``cache_pool`` and ``lock``, and builds the storage and lock
    factory it hands the factory.

    Attributes:
        policy: How the limiter counts hits.
        limit: The hits a window takes, or the tokens a bucket holds.
        interval: How long a window lasts: ``"15 minutes"``,
            ``"1 hour 30 minutes"``, or a :class:`~datetime.timedelta`.
        rate: How fast a bucket refills.
        anchor_at: Align fixed windows to a calendar starting at this
            instant — ISO 8601, read as UTC without a zone — instead of
            opening one on the first hit. Requires an interval of at least a
            month.
        limiters: The configured limiters a compound limiter combines, by
            name.
        keys: A key to use for some of the combined limiters instead of the
            one the compound limiter is created with — ``{"global": "all"}``
            to share one count across every caller.
        storage: ``"cache"`` for a cache pool, ``"in-memory"`` for this
            process only, a Redis DSN (``"redis://host:6379"``) to count
            atomically on the server with no lock, or a
            :class:`~xtr_dependency_injection.Reference` to a
            :class:`~xtr_rate_limiter.storage.StorageInterface` or a Redis
            client the container provides. Also ``env(...)``.
        cache_pool: The cache pool a ``"cache"`` storage keeps states in.
        lock: The lock around each read and write of a state: ``"auto"``, a
            lock resource's name, or ``None`` to lock within this process
            only. Unused in Redis, which needs none.
    """

    policy: Policy
    limit: int | None = None
    interval: IntervalLike | None = None
    rate: Rate | None = None
    anchor_at: datetime | str | None = None
    limiters: Sequence[str] = ()
    keys: Mapping[str, str] = field(default_factory=_no_keys)
    storage: str | Reference = CACHE_STORAGE
    cache_pool: str = DEFAULT_CACHE_POOL
    lock: str | None = AUTO_LOCK

    def __post_init__(self) -> None:
        """Refuse an unknown policy, or an option missing from it or foreign to it.

        Strings are compared, never tested for truth: an ``env(...)``
        placeholder refuses to be one while the kernel builds.

        Raises:
            InvalidArgumentError: When the configuration cannot be used.
            InvalidIntervalError: When the interval cannot be read.
        """
        if self.policy not in _POLICIES:
            expected = '", "'.join(sorted(_POLICIES))
            raise InvalidArgumentError(
                f'Unknown rate limiter policy "{self.policy}"; expected one of "{expected}".',
            )
        self._check_limit()
        self._check_interval()
        self._check_rate()
        self._check_compound()
        if self.storage == "":
            raise InvalidArgumentError("A rate limiter's storage cannot be empty.")
        if self.cache_pool == "":
            raise InvalidArgumentError("A rate limiter's cache pool cannot be empty.")
        if self.lock == "":
            raise InvalidArgumentError('A rate limiter\'s lock is a name, "auto" or None, not "".')

    def anchor(self) -> datetime | None:
        """Return :attr:`anchor_at` as a timezone-aware datetime; ``None`` when there is none.

        Raises:
            InvalidArgumentError: When the anchor cannot be read.
        """
        anchor = self.anchor_at
        if anchor is None:
            return None
        if isinstance(anchor, str):
            try:
                anchor = datetime.fromisoformat(anchor)
            except ValueError as error:
                raise InvalidArgumentError(f"Cannot read the anchor {anchor!r}.") from error
        return anchor if anchor.tzinfo is not None else anchor.replace(tzinfo=UTC)

    def parsed_interval(self) -> Interval:
        """Return :attr:`interval`, read.

        Raises:
            InvalidArgumentError: When the policy takes no interval.
        """
        if self.interval is None:
            raise InvalidArgumentError(f'The "{self.policy}" policy takes no interval.')
        return Interval.parse(self.interval)

    def _check_limit(self) -> None:
        if self.policy in _UNLIMITED:
            if self.limit is not None:
                raise InvalidArgumentError(f'The "{self.policy}" policy takes no limit.')
            return
        if self.limit is None:
            raise InvalidArgumentError(f'The "{self.policy}" policy needs a limit.')
        if self.limit < 1:
            raise InvalidArgumentError(
                f"Cannot set the limit to {self.limit}, as that would never accept any hit.",
            )

    def _check_interval(self) -> None:
        if self.policy not in _WINDOWS:
            if self.interval is not None:
                raise InvalidArgumentError(f'The "{self.policy}" policy takes no interval.')
            if self.anchor_at is not None:
                raise InvalidArgumentError('Only the "fixed_window" policy takes an anchor.')
            return
        if self.interval is None:
            raise InvalidArgumentError(f'The "{self.policy}" policy needs an interval.')
        interval = Interval.parse(self.interval)
        if self.anchor_at is None:
            return
        if self.policy != "fixed_window":
            raise InvalidArgumentError('Only the "fixed_window" policy takes an anchor.')
        _ = self.anchor()
        if interval.months == 0:
            raise InvalidArgumentError(
                "Aligning a fixed window to a calendar requires an interval of at least one month.",
            )

    def _check_rate(self) -> None:
        if self.policy == "token_bucket":
            if self.rate is None:
                raise InvalidArgumentError('The "token_bucket" policy needs a rate.')
        elif self.rate is not None:
            raise InvalidArgumentError(f'The "{self.policy}" policy takes no rate.')

    def _check_compound(self) -> None:
        if self.policy != "compound":
            if self.limiters or self.keys:
                raise InvalidArgumentError('Only the "compound" policy combines limiters.')
            return
        if isinstance(self.limiters, str) or not self.limiters:
            raise InvalidArgumentError(
                "A compound rate limiter needs a list of at least one limiter."
            )
        unknown = sorted(set(self.keys) - set(self.limiters))
        if unknown:
            raise InvalidArgumentError(
                f"A compound rate limiter has keys for limiters it does not combine: "
                f'"{", ".join(unknown)}".',
            )
