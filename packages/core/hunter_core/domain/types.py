"""Domain-wide value types: money, UUID v7 and UTC-aware datetimes.

CLAUDE.md hard rules enforced here: money and quantities are ``Decimal``
(never ``float``); timestamps are always timezone-aware UTC.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal
from typing import Any

import uuid6

Money = Decimal
"""Alias documenting intent: any field holding price/qty/PnL/fee is ``Decimal``."""


def to_money(value: Any) -> Decimal:
    """Build a ``Decimal`` for a money/quantity field.

    Rejects ``float`` with ``TypeError``: binary floating point cannot
    represent money exactly, so no float ever becomes a ``Decimal`` here
    (constructing ``Decimal(0.1)`` silently keeps the float's rounding
    error, which is exactly what must never happen for money). Typed
    ``Any`` on purpose — this is a runtime guard against callers that are
    not type-checked (e.g. a value freshly decoded from JSON or an env var).
    """
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise TypeError(f"to_money() rejects {type(value).__name__}; use str, int or Decimal")
    return value if isinstance(value, Decimal) else Decimal(value)


def quantize(value: Decimal, step: Decimal) -> Decimal:
    """Round ``value`` down to the nearest multiple of ``step`` (exchange step/tick size)."""
    if step <= 0:
        raise ValueError("step must be positive")
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def utcnow() -> datetime:
    """Current time, timezone-aware, UTC."""
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    """Return ``dt`` converted to UTC; raise ``ValueError`` if ``dt`` is naive."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("naive datetime is not allowed; every timestamp must be tz-aware UTC")
    return dt.astimezone(UTC)


def uuid7() -> uuid.UUID:
    """A time-ordered UUID v7, used for every primary key (see DATABASE.md §1)."""
    return uuid6.uuid7()
