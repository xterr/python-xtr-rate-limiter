"""States kept in this process, for a single worker or a test."""

from __future__ import annotations

import pickle
from typing import TYPE_CHECKING, Final, cast, final

from typing_extensions import override
from xtr_clock import Clock

from .storage_interface import StorageInterface

if TYPE_CHECKING:
    from xtr_clock import ClockInterface

    from xtr_rate_limiter.limiter_state_interface import LimiterStateInterface

__all__ = ["InMemoryStorage"]

_PRUNE_EVERY: Final = 1_000
"""How many saves pass between two sweeps of the expired states."""


@final
class InMemoryStorage(StorageInterface):
    """Keeps states in a dictionary of this process, each until it expires.

    A state is copied in and out, so a limiter changing the state it fetched
    changes nothing here until it saves it. Nothing is shared with another
    process: each counts its own hits.

    Every thousand saves the expired states are swept out, so a process
    limiting by client address does not keep one state per address it ever
    saw.
    """

    __slots__ = ("_clock", "_saves", "_states")

    def __init__(self, clock: ClockInterface | None = None) -> None:
        """Keep states, expiring them by ``clock``; the clock in force when ``None``."""
        self._clock: ClockInterface = clock if clock is not None else Clock()
        self._states: dict[str, tuple[float | None, bytes]] = {}
        self._saves = 0

    def __len__(self) -> int:
        """Return how many states are kept, expired ones not yet swept included."""
        return len(self._states)

    @override
    async def save(self, state: LimiterStateInterface, /) -> None:
        """Keep a copy of ``state`` until it expires."""
        expires_at = state.expires_at
        if expires_at is None and state.id in self._states:
            expires_at = self._states[state.id][0]
        self._states[state.id] = (expires_at, pickle.dumps(state))
        self._saves += 1
        if self._saves % _PRUNE_EVERY == 0:
            self._prune()

    @override
    async def fetch(self, state_id: str, /) -> LimiterStateInterface | None:
        """Return a copy of the state kept under ``state_id``, unless it expired."""
        kept = self._states.get(state_id)
        if kept is None:
            return None
        expires_at, state = kept
        if expires_at is not None and expires_at <= self._clock.now().timestamp():
            del self._states[state_id]
            return None
        # Only this storage wrote it, from a state it was handed.
        return cast("LimiterStateInterface", pickle.loads(state))  # noqa: S301

    @override
    async def delete(self, state_id: str, /) -> None:
        """Forget the state kept under ``state_id``."""
        _ = self._states.pop(state_id, None)

    def _prune(self) -> None:
        now = self._clock.now().timestamp()
        expired = [
            state_id
            for state_id, (expires_at, _) in self._states.items()
            if expires_at is not None and expires_at <= now
        ]
        for state_id in expired:
            del self._states[state_id]
