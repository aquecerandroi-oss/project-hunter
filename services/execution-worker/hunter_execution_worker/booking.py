"""What a fill is really booked at, and the rounding that costs.

Split out of :mod:`hunter_execution_worker.rows` because it is a different
question: ``rows`` writes, this decides *what number* is written.

**The booked price is the ledger's authority.** ``fills.price`` is
``NUMERIC(28,10)`` and the wallet's cash is rebuilt as ``Σ qty × price``
(``LedgerRepository.reconcile_cash``), so the price written is
``gross_quote / filled_qty`` rounded to ten decimals, and the difference from
the walk's own ``gross_quote`` is published on the fill as
``booking_residual_quote`` instead of being absorbed silently. It is bounded by
``filled_qty × 5e-11`` and is exactly zero whenever the walk touched a single
level — which is the case in every closed number of
``spec-T3.9-verificacoes.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Any

from hunter_core.strategies.numeric import CONTEXT

if TYPE_CHECKING:
    from hunter_core.execution.adapter import ExecutionReport

__all__ = ["PRICE_QUANTUM", "Booking", "book_fill", "fill_metadata"]

PRICE_QUANTUM = Decimal("0.0000000001")
"""Ten decimals — the scale of ``NUMERIC(28,10)``, and of nothing else."""

_ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class Booking:
    """What the ledger will actually record for one filled attempt."""

    price: Decimal
    gross: Decimal
    """``filled_qty × price`` — the number the wallet's cash is rebuilt from."""
    residual: Decimal
    """``report.gross_quote − gross``. Published, never absorbed."""

    @property
    def exact(self) -> bool:
        return self.residual == _ZERO


def book_fill(report: ExecutionReport) -> Booking:
    """The price to store and the rounding it costs, both stated."""
    if report.filled_qty <= 0:
        return Booking(price=_ZERO, gross=_ZERO, residual=_ZERO)
    with localcontext(CONTEXT):
        price = (report.gross_quote / report.filled_qty).quantize(PRICE_QUANTUM)
        gross = (report.filled_qty * price).quantize(PRICE_QUANTUM)
        return Booking(price=price, gross=gross, residual=report.gross_quote - gross)


def fill_metadata(report: ExecutionReport, booking: Booking, source: str) -> dict[str, Any]:
    """The provenance a fill carries so a replay can be judged, not guessed."""
    return {
        "submitted_qty": str(report.submitted_qty) if report.submitted_qty is not None else None,
        "decision_fingerprint": report.decision_fingerprint,
        "gross_quote": str(report.gross_quote),
        "booking_residual_quote": str(booking.residual),
        "vwap": str(report.vwap) if report.vwap is not None else None,
        "fee_quote_equivalent": (
            str(report.fee.quote_equivalent)
            if report.fee is not None and report.fee.quote_equivalent is not None
            else None
        ),
        "net_base_delta": str(report.net_base_delta),
        "net_quote_delta": str(report.net_quote_delta),
        "book_sequence": report.book_sequence,
        "book_received_at": (
            report.book_received_at.isoformat() if report.book_received_at else None
        ),
        "latency_ms": report.latency_ms,
        "depth_exhausted": report.depth_exhausted,
        "marking_policy_version": report.marking_policy_version,
        "book_policy_version": report.book_policy_version,
        "execution_policy_version": report.execution_policy_version,
        "market_data_source": source,
        "slippage_vs_plan_quote": (
            str(report.slippage_vs_plan_quote) if report.slippage_vs_plan_quote else None
        ),
        "slippage_vs_plan_bps": (
            str(report.slippage_vs_plan_bps) if report.slippage_vs_plan_bps else None
        ),
        "trigger_trade_id": report.trigger_trade_id,
        "observed_trade_id": report.observed_trade_id,
        "reason": report.reason,
        "alert": report.alert,
    }
