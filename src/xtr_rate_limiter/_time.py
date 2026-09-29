"""Instants as the limiters count them: seconds since the epoch, shown as dates."""

from __future__ import annotations

from datetime import UTC, datetime

from xtr_clock import DatePoint

__all__ = ["instant"]


def instant(timestamp: float) -> DatePoint:
    """Return the moment ``timestamp`` seconds after the epoch, in UTC."""
    return DatePoint.from_datetime(datetime.fromtimestamp(timestamp, UTC))
