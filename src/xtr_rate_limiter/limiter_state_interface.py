"""What a storage keeps for a limiter."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["LimiterStateInterface"]


@runtime_checkable
class LimiterStateInterface(Protocol):
    """The state of one limiter for one key, as a storage keeps it.

    A state is a plain object a storage may copy, pickle or hand back as it
    is. It knows the moment it is no longer worth keeping, so a storage lets
    it go then.
    """

    @property
    def id(self) -> str:
        """The limiter's id and key, which the state is stored under."""
        ...

    @property
    def expires_at(self) -> float | None:
        """When the state can be forgotten, in seconds since the epoch; ``None`` for never."""
        ...
