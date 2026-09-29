"""Where a limiter keeps its state between hits."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from xtr_rate_limiter.limiter_state_interface import LimiterStateInterface

__all__ = ["StorageInterface"]


@runtime_checkable
class StorageInterface(Protocol):
    """Keeps limiter states by id: fetch one, save one, delete one.

    A storage is deliberately plain — nothing here is atomic. A limiter keeps
    two callers from interleaving by holding a lock on the id around each
    fetch and save, so a storage only has to keep what it is given and let it
    go once its :attr:`~LimiterStateInterface.expires_at` passes.
    """

    async def save(self, state: LimiterStateInterface, /) -> None:
        """Keep ``state`` under its id until it expires."""
        ...

    async def fetch(self, state_id: str, /) -> LimiterStateInterface | None:
        """Return the state kept under ``state_id``; ``None`` when there is none."""
        ...

    async def delete(self, state_id: str, /) -> None:
        """Forget the state kept under ``state_id``; an id holding nothing is fine."""
        ...
