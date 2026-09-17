"""Injected/consistent time handling for the observability layer.

All observability timestamps use the same representation: ISO-8601 UTC
(e.g. ``2026-01-01T00:00:00.000000+00:00``). A :class:`Clock` can be replaced
with a fixed timestamp factory in tests so assertions never depend on the
machine being fast or slow.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

NowFn = Callable[[], str]


def default_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def parse_ts(value: Any) -> datetime | None:
    """Parse an ISO-8601 (or naive) timestamp into a datetime.

    Returns None when ``value`` is empty/None. Naive timestamps are left naive;
    duration calculations only ever subtract timestamps produced by the same
    clock, so this stays consistent.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def seconds_between(start: Any, end: Any) -> float:
    """Return ``end - start`` in seconds, or 0.0 when either is missing."""
    start_dt = parse_ts(start)
    end_dt = parse_ts(end)
    if start_dt is None or end_dt is None:
        return 0.0
    return max(0.0, (end_dt - start_dt).total_seconds())


class Clock:
    """Injectable timestamp provider for deterministic observability tests."""

    def __init__(self, now: NowFn | None = None) -> None:
        self._now = now or default_now

    def now(self) -> str:
        return self._now()


__all__ = ["Clock", "NowFn", "default_now", "parse_ts", "seconds_between"]