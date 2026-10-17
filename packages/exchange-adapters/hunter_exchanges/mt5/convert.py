"""Decimal <-> float, at the MT5 boundary only (contract I-$-1).

The vendor API speaks ``float``; the rest of the system speaks ``Decimal``. Nothing outside this
module (and the request builder that calls it) ever holds a float for a price, volume or
amount. Prices and volumes live on a grid (``trade_tick_size``, ``volume_step``):

* **out** (:func:`to_float_on_grid`): the value must already be an exact multiple of the step;
  otherwise it is refused — silently rounding a stop would move risk.
* **in** (:func:`from_float_on_grid`): the float is snapped to the nearest multiple of the step;
  if it is further than a tiny fraction of a step it is *not* a grid value and is refused rather
  than invented. One ULP of float noise (``130005.00000000001``) snaps back exactly.

Money that is not on a grid (balance, equity, margin, commissions) is converted from the float's
shortest repr (:func:`money_from_float`, :func:`decimal_from_float`), never from its binary
expansion.

**Supported range.** The snap tolerance is ``1e-6`` of a step, which float resolution meets
while ``price / step`` stays below about a billion (WIN: ~26 000 steps). Beyond it a value is
either exact or refused with :class:`OffGridError` - never a different number
(``tests/mt5/test_convert.py`` proves both).

Time: the API's integers are epoch seconds / milliseconds. They are converted to tz-aware UTC
here; naive datetimes are refused.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Context, Decimal

__all__ = [
    "OffGridError",
    "ceil_to_tick",
    "decimal_from_float",
    "decimal_from_number",
    "epoch_from_utc",
    "floor_to_tick",
    "from_float_on_grid",
    "money_from_float",
    "nearest_to_tick",
    "number_on_grid_or_none",
    "to_float_on_grid",
    "utc_from_epoch",
    "utc_from_msc",
]

_CTX = Context(prec=50)
# A float value is "on the grid" if it is within this fraction of a step from a multiple.
_GRID_TOLERANCE = Decimal("1e-6")


class OffGridError(ValueError):
    """A price or volume is not an exact multiple of its step."""


def _require_step(step: object) -> None:
    if not isinstance(step, Decimal):
        raise TypeError(f"step must be a Decimal, got {type(step).__name__}")
    if not step.is_finite() or step <= 0:
        raise ValueError("step must be a positive finite Decimal")


def _require_decimal(value: object) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"value must be a Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise ValueError("value must be finite")


def _require_finite(value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"expected a finite float, got {value!r}")


def _steps(value: Decimal, step: Decimal) -> Decimal:
    return _CTX.divide(value, step)


def floor_to_tick(value: Decimal, tick: Decimal) -> Decimal:
    _require_decimal(value)
    _require_step(tick)
    return _steps(value, tick).to_integral_value(rounding=ROUND_FLOOR) * tick


def ceil_to_tick(value: Decimal, tick: Decimal) -> Decimal:
    _require_decimal(value)
    _require_step(tick)
    return _steps(value, tick).to_integral_value(rounding=ROUND_CEILING) * tick


def nearest_to_tick(value: Decimal, tick: Decimal) -> Decimal:
    _require_decimal(value)
    _require_step(tick)
    return _steps(value, tick).to_integral_value(rounding=ROUND_HALF_EVEN) * tick


def to_float_on_grid(value: Decimal, step: Decimal) -> float:
    """``float(value)`` iff ``value`` is an exact multiple of ``step``; else :class:`OffGridError`."""
    _require_decimal(value)
    _require_step(step)
    steps = _steps(value, step)
    if steps != steps.to_integral_value():
        raise OffGridError(f"{value} is not a multiple of {step}")
    return float(value)


def from_float_on_grid(value: float, step: Decimal) -> Decimal:
    """Snap ``value`` to the nearest multiple of ``step`` (exact ``Decimal``) or refuse."""
    _require_finite(value)
    _require_step(step)
    exact = Decimal(value)  # exact binary expansion; no repr guesswork
    steps = _steps(exact, step)
    nearest = steps.to_integral_value(rounding=ROUND_HALF_EVEN)
    if abs(steps - nearest) > _GRID_TOLERANCE:
        raise OffGridError(f"{value!r} is not on the grid of {step}")
    return nearest * step


def decimal_from_float(value: float) -> Decimal:
    """The float's shortest repr as a ``Decimal`` (no exponent form), for non-grid numbers."""
    _require_finite(value)
    dec = Decimal(repr(value))
    if dec == 0:
        return Decimal(0)
    return Decimal(format(dec.normalize(), "f"))


def money_from_float(value: float, digits: int) -> Decimal:
    """An amount in the account currency, quantized to its ``digits`` (half-even)."""
    _require_finite(value)
    return Decimal(repr(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_EVEN)


def utc_from_epoch(seconds: int | float) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)


def utc_from_msc(milliseconds: int) -> datetime:
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=milliseconds)


def epoch_from_utc(moment: datetime) -> int:
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise ValueError("naive datetime is not allowed; pass a tz-aware datetime")
    return int(moment.timestamp())


def decimal_from_number(value: object) -> Decimal | None:
    """A numeric field of a vendor result as ``Decimal``; ``None`` if it is not a real number.

    ``bool`` is refused (``True`` is not a margin of 1), and so are ``NaN``/``inf``, strings and
    ``None`` - the caller decides what "unavailable" means; it is never zero.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, int):
        return Decimal(value)
    return decimal_from_float(value) if math.isfinite(value) else None


def number_on_grid_or_none(value: object, step: Decimal | None) -> Decimal | None:
    """A price/volume of an ``order_send`` result: ``0`` means "not applicable" (``None``);
    on-grid values snap exactly, off-grid ones keep their shortest repr."""
    number = decimal_from_number(value)
    if number is None or number == 0:
        return None
    if step is None:
        return number
    try:
        return from_float_on_grid(float(number), step)
    except OffGridError:
        return number
