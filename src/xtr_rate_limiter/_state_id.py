"""The name one limiter's state is kept under: its limit's name and its key."""

from __future__ import annotations

__all__ = ["state_id"]


def state_id(limiter_id: str, key: str | None) -> str:
    """Return the name the state of ``key`` under the limit ``limiter_id`` is kept as.

    The limit's name is prefixed with its own length, so no two
    name-and-key pairs can ever spell the same state: the limit ``"x"``
    keyed ``"a-b"`` and the limit ``"x-a"`` keyed ``"b"`` would otherwise
    share a count.
    """
    return f"{len(limiter_id)}:{limiter_id}:{key or ''}"
