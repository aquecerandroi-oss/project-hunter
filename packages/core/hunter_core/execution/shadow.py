"""``ShadowExecutionAdapter``: it writes down what would have been attempted.

``docs/PIPELINE.md`` §8.6 — shadow records orders and fills with
``simulated=true`` and ``execution_mode=shadow`` "sem alterar cash. Idêntico ao
paper em tudo o mais". T3.4 makes the first half structural: this adapter never
produces a fill, so there is no report a ledger could turn into money. The
status is ``recorded`` and both deltas are zero.

Why not "paper with the balance ignored": because then a shadow report would be
indistinguishable from a paper one, and the only thing standing between the two
would be a caller remembering not to apply it. Here the difference is in the
object.

Triggers are still evaluated: deciding that a stop was touched is an
observation, not an effect, and the shadow lab needs it to be the same
observation the wallet makes.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import ExecutionMode
from hunter_core.domain.market import NormalizedOrderBook, NormalizedTrade
from hunter_core.execution.adapter import ExecutionReport, FeeSchedule, SpotFilters
from hunter_core.execution.entries import MarketEntryOrder
from hunter_core.execution.intents import ExitAttempt
from hunter_core.execution.pricing import EXECUTION_POLICY_VERSION
from hunter_core.execution.triggers import (
    MARKING_POLICY_VERSION,
    MarkingPolicy,
    ProtectedPosition,
    TriggerEvaluation,
    check_triggers,
)

__all__ = ["ShadowExecutionAdapter"]


class ShadowExecutionAdapter:
    """Records every attempt; fills none of them."""

    mode = ExecutionMode.SHADOW

    def __init__(self, *, marking_policy: MarkingPolicy | None = None) -> None:
        self.marking_policy = marking_policy or MarkingPolicy()
        self._submissions: list[ExecutionReport] = []

    @property
    def submissions(self) -> tuple[ExecutionReport, ...]:
        """Everything this adapter was asked to do, in order."""
        return tuple(self._submissions)

    def submit_market_entry(
        self,
        order: MarketEntryOrder,
        book: NormalizedOrderBook | None,
        last_trade: NormalizedTrade | None,
        filters: SpotFilters,
        fees: FeeSchedule,
        now: datetime,
        **_ignored: Any,
    ) -> ExecutionReport:
        return self._record(qty=order.qty, now=now, **order.report_identity(last_trade))

    def submit_protection_exit(
        self,
        attempt: ExitAttempt,
        position_qty: Decimal,
        book: NormalizedOrderBook | None,
        last_trade: NormalizedTrade | None,
        filters: SpotFilters,
        fees: FeeSchedule,
        now: datetime,
        **_ignored: Any,
    ) -> ExecutionReport:
        return self._record(
            qty=min(attempt.qty, max(position_qty, Decimal(0))),
            now=now,
            **attempt.report_identity(last_trade),
        )

    def check_triggers(
        self,
        position: ProtectedPosition,
        trades: Sequence[NormalizedTrade],
        now: datetime,
        *,
        tape_gap: bool = False,
        last_accepted_trade_id: int | None = None,
    ) -> TriggerEvaluation:
        return check_triggers(
            position,
            trades,
            now,
            policy=self.marking_policy,
            last_accepted_trade_id=last_accepted_trade_id,
            tape_gap=tape_gap,
        )

    def _record(self, *, kind: str, qty: Decimal, now: datetime, **fields: Any) -> ExecutionReport:
        report = ExecutionReport(
            kind=kind,  # type: ignore[arg-type]
            status="recorded",
            mode=self.mode,
            requested_qty=max(qty, Decimal(0)),
            unfilled_qty=max(qty, Decimal(0)),
            reason="shadow mode records the attempt and never fills it",
            executed_at=now,
            marking_policy_version=MARKING_POLICY_VERSION,
            execution_policy_version=EXECUTION_POLICY_VERSION,
            **fields,
        )
        self._submissions.append(report)
        return report
