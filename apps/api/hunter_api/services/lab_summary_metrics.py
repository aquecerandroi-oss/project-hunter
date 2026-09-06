"""Pure ``Decimal`` math for ``/lab/shadow/summary`` — no IO, no float, ever.

Split out of ``services/lab_summary.py`` for the 350-line budget and because
this half is exactly what a unit test wants: no session, no request, just
rows in and numbers out.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState
from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from hunter_api.repositories.lab_summary import OutcomeRow

__all__ = [
    "NO_ENTRY_REASONS",
    "RateResult",
    "ProfitFactorResult",
    "SumResult",
    "bucket_censored_reason",
    "expectancy",
    "is_evaluable",
    "quantize4",
    "r_ex_funding_of",
    "rate",
    "profit_factor",
    "sum_of",
    "touch_counts",
]

FOUR_PLACES = Decimal("0.0001")

NO_ENTRY_REASONS = ("late:delay", "late:missed_open", "late:unconfirmed", "geometry")
"""The named populations SHADOW-LAB.md's notes-S2.md §14 requires apart —
anything else falls into ``other`` rather than being dropped."""

_GAP_SUFFIXES = ("failed", "unregistered", "stalled")


def quantize4(value: Decimal) -> Decimal:
    return value.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def bucket_censored_reason(reason: str | None) -> str:
    """``gap:<minute>:<why>`` -> ``gap:<why>``; ``blocked:<symbol>`` -> ``blocked``.

    Local data can carry a ``gap:<minute>`` with no third segment (a
    strategy-worker image older than notes-S2.md §16's fix) — that falls into
    ``gap:unknown`` instead of being silently dropped.
    """
    if reason is None:
        return "other"
    if reason.startswith("blocked:"):
        return "blocked"
    if reason.startswith("gap:"):
        parts = reason.split(":")
        suffix = parts[-1] if len(parts) >= 3 else None
        return f"gap:{suffix}" if suffix in _GAP_SUFFIXES else "gap:unknown"
    return "other"


def is_evaluable(row: OutcomeRow, as_of: datetime) -> bool:
    """The maturity gate contract-S3-lab.md's Astra review added (must-fix 2).

    Terminal alone is not enough: a decision whose horizon has not fully
    elapsed by ``as_of`` is excluded even if it already resolved early, so a
    recent window cannot over-represent fast stops over trades still waiting
    to reach ``expired``. ``exit_ts <= as_of`` is the belt-and-braces guard
    against reading a future exit when ``as_of`` is in the past — this is
    never a historical reconstruction of ``tracking_state`` itself, only a
    filter on which decisions are counted (declared in the contract).
    """
    if row.tracking_state is not ShadowTrackingState.TERMINAL:
        return False
    if row.exit_ts is None or row.exit_ts > as_of:
        return False
    entry_plan: dict[str, Any] = row.meta.get("entry_plan") or {}
    entry_bar_open_raw: Any = entry_plan.get("entry_bar_open")
    horizon_s: Any = row.meta.get("horizon_s")
    if entry_bar_open_raw is None or horizon_s is None:
        return False
    entry_bar_open = ensure_utc(datetime.fromisoformat(str(entry_bar_open_raw)))
    matured_at = entry_bar_open + timedelta(seconds=int(horizon_s))
    return matured_at <= as_of


def r_ex_funding_of(row: OutcomeRow) -> Decimal | None:
    raw = row.meta.get("r_ex_funding")
    return None if raw is None else Decimal(str(raw))


@dataclass(frozen=True, slots=True)
class RateResult:
    value: Decimal | None
    reason: str | None


def rate(numerator: int, denominator: int, *, reason_if_empty: str) -> RateResult:
    if denominator == 0:
        return RateResult(None, reason_if_empty)
    return RateResult(quantize4(Decimal(numerator) / Decimal(denominator)), None)


@dataclass(frozen=True, slots=True)
class SumResult:
    value: Decimal | None
    reason: str | None
    count: int


def sum_of(values: list[Decimal]) -> SumResult:
    if not values:
        return SumResult(None, "no_sample", 0)
    return SumResult(quantize4(sum(values, Decimal(0))), None, len(values))


@dataclass(frozen=True, slots=True)
class ProfitFactorResult:
    value: Decimal | None
    reason: str | None
    sum_positive: Decimal
    sum_negative_abs: Decimal
    sample_size: int


def profit_factor(values: list[Decimal]) -> ProfitFactorResult:
    """Sum and divide at full precision; quantize only the numbers presented.

    Astra, diff review, must-fix 1: rounding the sums to 4 places *before*
    checking for losses and dividing made a tiny-but-real loss
    (``-0.00004``) compare equal to zero and a genuine PF of 25000 come back
    ``null``. The intermediate values stay exact; ``quantize4`` only touches
    what the caller sees.
    """
    if not values:
        return ProfitFactorResult(None, "no_sample", Decimal("0.0000"), Decimal("0.0000"), 0)
    raw_positive = sum((v for v in values if v > 0), Decimal(0))
    raw_negative_abs = -sum((v for v in values if v < 0), Decimal(0))
    positive = quantize4(raw_positive)
    negative_abs = quantize4(raw_negative_abs)
    if raw_negative_abs == 0:
        return ProfitFactorResult(None, "no_losses", positive, negative_abs, len(values))
    return ProfitFactorResult(
        quantize4(raw_positive / raw_negative_abs), None, positive, negative_abs, len(values)
    )


def expectancy(values: list[Decimal]) -> RateResult:
    if not values:
        return RateResult(None, "no_sample")
    total = sum(values, Decimal(0))
    return RateResult(quantize4(total / Decimal(len(values))), None)


def touch_counts(rows: list[OutcomeRow]) -> tuple[int, int]:
    target = sum(1 for r in rows if r.result is OutcomeResult.TARGET)
    stop = sum(1 for r in rows if r.result is OutcomeResult.STOP)
    return target, stop
