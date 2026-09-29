"""Where the limiters built in code keep their state."""

from __future__ import annotations

from dataclasses import dataclass

from xtr_dependency_injection import Reference

from xtr_rate_limiter.exception import InvalidArgumentError
from xtr_rate_limiter.limiter_config import AUTO_LOCK, CACHE_STORAGE, DEFAULT_CACHE_POOL

__all__ = ["BuilderConfig"]


@dataclass(frozen=True, slots=True)
class BuilderConfig:
    """Configuration for the :class:`~xtr_rate_limiter.RateLimiterBuilder` service.

    The builder counts over a storage, so its limiters keep their state in a
    cache pool, in this process, or in a storage the container provides —
    not in Redis, which counts with scripts of its own.

    Attributes:
        storage: ``"cache"``, ``"in-memory"``, or a
            :class:`~xtr_dependency_injection.Reference` to a
            :class:`~xtr_rate_limiter.storage.StorageInterface`.
        cache_pool: The cache pool a ``"cache"`` storage keeps states in.
        lock: The lock around each read and write of a state: ``"auto"``, a
            lock resource's name, or ``None`` to lock within this process
            only.
    """

    storage: str | Reference = CACHE_STORAGE
    cache_pool: str = DEFAULT_CACHE_POOL
    lock: str | None = AUTO_LOCK

    def __post_init__(self) -> None:
        """Refuse an empty storage, cache pool or lock name.

        Strings are compared, never tested for truth: an ``env(...)``
        placeholder refuses to be one while the kernel builds.

        Raises:
            InvalidArgumentError: When one of them cannot be used.
        """
        if not isinstance(self.storage, (str, Reference)):  # pyright: ignore[reportUnnecessaryIsInstance] -- configs are written by hand; the annotation is not enforced
            raise InvalidArgumentError(
                f"The rate limiter builder's storage must be a string or a Reference, "
                f"got {self.storage!r}.",
            )
        if self.storage == "":
            raise InvalidArgumentError("The rate limiter builder's storage cannot be empty.")
        if self.cache_pool == "":
            raise InvalidArgumentError("The rate limiter builder's cache pool cannot be empty.")
        if self.lock == "":
            raise InvalidArgumentError(
                'The rate limiter builder\'s lock is a name, "auto" or None, not "".',
            )
