"""Price levels at the database's own scale — ``NUMERIC(28,10)``.

A ``Decimal`` computed with 28 significant digits and a ``NUMERIC(28,10)``
column are not the same number: writing ``1.23456789012345`` and reading it back
gives ``1.2345678901``. If the worker kept the in-memory value and the restarted
worker read the stored one, the *same* tracking would use two different stops —
one before the restart and one after — and neither the outcome nor the R would
be reproducible.

So every level is put at the storage scale **before** it is written, and every
consumer uses the stored value. The rounding is explicit and half-even, inside
the strategies' declared context, so it is the same on every machine
(notes-S1.md §12, "escala do banco").
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal, InvalidOperation, localcontext

from hunter_core.strategies.numeric import CONTEXT

DB_PRECISION = 28
DB_SCALE = 10
_QUANTUM = Decimal(1).scaleb(-DB_SCALE)
_MAX = Decimal(10) ** (DB_PRECISION - DB_SCALE)

__all__ = ["DB_PRECISION", "DB_SCALE", "to_db_scale", "to_db_scale_all"]


def to_db_scale(value: Decimal) -> Decimal:
    """``value`` as ``NUMERIC(28,10)`` will store it. Refuses what will not fit."""
    with localcontext(CONTEXT):
        if not value.is_finite():
            raise ValueError(f"{value!r} is not a finite level")
        if abs(value) >= _MAX:
            raise ValueError(f"{value!r} does not fit NUMERIC({DB_PRECISION},{DB_SCALE})")
        try:
            return value.quantize(_QUANTUM)
        except InvalidOperation as exc:  # pragma: no cover - guarded by _MAX above
            raise ValueError(f"{value!r} cannot be stored as a level") from exc


def to_db_scale_all(values: Iterable[Decimal]) -> tuple[Decimal, ...]:
    """:func:`to_db_scale` over a sequence of levels, order preserved."""
    return tuple(to_db_scale(value) for value in values)
