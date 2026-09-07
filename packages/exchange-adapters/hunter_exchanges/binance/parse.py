"""Primitive value coercion for Binance payloads — the four checks every
parser in this package starts from, and the venue code they all stamp.

Split out of :mod:`.normalize` (T3.0b, 350-line budget): ``normalize`` parses
*endpoints*, and these parse *values*. Three modules and the whole spot
package already reached into ``normalize`` for them, so they were never
specific to it. ``normalize`` re-exports every name here; nothing had to move.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from hunter_exchanges.base import MalformedMessage

__all__ = [
    "EXCHANGE",
    "ms_to_datetime",
    "require_field",
    "to_decimal",
    "to_decimal_or_none",
]

EXCHANGE = "binance"


def to_decimal(value: Any, *, field: str) -> Decimal:
    """``Decimal(value)`` for a ``str``/``int``/``Decimal`` value.

    Rejects ``bool``, ``None`` and, per CLAUDE.md ("money is Decimal, never
    float"), ``float`` too — Binance always sends prices/quantities as JSON
    strings. T1.6b-A (~5.7% self time at 200 markets, ``t16b-profile.md``):
    skips the redundant ``str(value)`` for the ``str`` case (always true for
    a real Binance field) — same result either way for ``int``/``Decimal``.
    """
    if isinstance(value, bool) or value is None:
        raise MalformedMessage(
            f"expected a decimal string for {field!r}, got {value!r}", exchange=EXCHANGE
        )
    if isinstance(value, float):
        raise MalformedMessage(
            f"refusing a float for {field!r}: {value!r} (use a string)", exchange=EXCHANGE
        )
    if not isinstance(value, (str, int, Decimal)):
        raise MalformedMessage(
            f"expected a decimal string for {field!r}, got {value!r}", exchange=EXCHANGE
        )
    try:
        return Decimal(value) if isinstance(value, str) else Decimal(str(value))
    except InvalidOperation as exc:
        raise MalformedMessage(
            f"invalid decimal for {field!r}: {value!r}", exchange=EXCHANGE
        ) from exc


def to_decimal_or_none(value: Any, *, field: str) -> Decimal | None:
    return None if value is None else to_decimal(value, field=field)


def ms_to_datetime(value: Any, *, field: str) -> datetime:
    """Epoch milliseconds (Binance's native timestamp unit) -> UTC ``datetime``."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise MalformedMessage(
            f"expected an epoch-ms int for {field!r}, got {value!r}", exchange=EXCHANGE
        )
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def require_field(raw: dict[str, Any], field: str) -> Any:
    if field not in raw:
        raise MalformedMessage(f"missing field {field!r} in {raw!r}", exchange=EXCHANGE)
    return raw[field]
