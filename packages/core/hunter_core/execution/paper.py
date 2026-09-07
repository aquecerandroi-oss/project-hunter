"""``PaperExecutionAdapter``: a simulated fill that can only say what the book proved.

Pure by construction — an order, a book, a trade, the filters, the fee schedule
and an instant go in, an :class:`~hunter_core.execution.adapter.ExecutionReport`
comes out. No clock, no database, no balance: the ledger (T3.3) applies the two
deltas the report publishes, in the transaction that also moves the intention
and the participation ledger. Two writers of one balance is what that avoids.

The rules, each with its own test: **the book has to be this market's**;
**filters first** (round down to the step, refuse below a floor *with the
filter's reason*, never round up, never judged against a trade we have not
received); **one walk, over the eligible book only**, after the declared latency,
``already_consumed`` so re-handing a snapshot restores no depth; **the fee in the
asset it is really charged in**; **an entry ends** with its remainder cancelled
while **a protection does not** — nothing usable to fill against leaves it
``pending_degraded`` with an alert, and a candle never supplies a retroactive
fill; and **a fill worse than the plan is published, not corrected**.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import ExecutionMode, OrderSide
from hunter_core.domain.market import NormalizedOrderBook, NormalizedTrade
from hunter_core.execution.adapter import (
    ExecutionJournal,
    ExecutionReport,
    FeeSchedule,
    LevelFill,
    Residual,
    SpotFilters,
)
from hunter_core.execution.book_walk import BookVerdict, BookWalk, walk_book
from hunter_core.execution.entries import MarketEntryOrder
from hunter_core.execution.idempotency import decision_fingerprint, guard_replay
from hunter_core.execution.intents import ExitAttempt
from hunter_core.execution.pricing import (
    ExecutionPolicy,
    apply_model_slippage,
    eligible_for,
    mark_price,
    policy_versions,
    price_band_breach,
    reference_fields,
    residual_for,
    slippage_vs_plan,
    taker_fee,
    untradable_reason,
)
from hunter_core.execution.triggers import (
    ProtectedPosition,
    TriggerEvaluation,
    check_triggers,
    usable_trade,
)

__all__ = ["PaperExecutionAdapter"]

_MINIMUM_REASONS = frozenset({"min_qty", "min_notional"})
"""The only refusals about a *quantity* too small to sell; the rest is unavailability."""


class PaperExecutionAdapter:
    """Simulated execution against the real spot book."""

    mode = ExecutionMode.PAPER

    def __init__(
        self, *, policy: ExecutionPolicy | None = None, journal: ExecutionJournal | None = None
    ) -> None:
        self.policy = policy or ExecutionPolicy()
        self.journal = journal

    def submit_market_entry(
        self,
        order: MarketEntryOrder,
        book: NormalizedOrderBook | None,
        last_trade: NormalizedTrade | None,
        filters: SpotFilters,
        fees: FeeSchedule,
        now: datetime,
        *,
        avg_price: Decimal | None = None,
        already_consumed: Sequence[LevelFill] = (),
        previous_book_sequence: int | None = None,
    ) -> ExecutionReport:
        """One attempt to buy; whatever does not fill is cancelled for good."""
        recorded = self._replay(order.execution_key)
        if recorded is not None:
            return guard_replay(
                recorded,
                submitted_qty=order.qty,
                decision=decision_fingerprint(order.decision),
            )
        common = order.report_identity(last_trade)
        market = (order.decision.market.exchange, order.decision.market.symbol)
        usable, _ = usable_trade(last_trade, now=now, policy=self.policy.marking_policy)
        common |= reference_fields(usable, avg_price, now=now, policy=self.policy)
        verdict = filters.check_market_order(
            order.qty, avg_price=avg_price, last_price=None if usable is None else usable.price
        )
        if not verdict.ok:
            return self._no_fill(common, verdict.qty, verdict.reason or "filter", now)
        book_verdict = eligible_for(
            self.policy,
            book,
            decision_at=order.decision_at,
            now=now,
            side=OrderSide.BUY,
            previous_sequence=previous_book_sequence,
            market=market,
        )
        if not book_verdict.eligible or book is None:
            return self._no_fill(common, verdict.qty, book_verdict.reason, now)
        walk = walk_book(book, verdict.qty, side=OrderSide.BUY, already_consumed=already_consumed)
        if walk.filled_qty <= 0:
            return self._no_fill(common, verdict.qty, "no_depth", now)
        gross, vwap = apply_model_slippage(walk, side=OrderSide.BUY, policy=self.policy)
        if price_band_breach(filters, side=OrderSide.BUY, fill_price=vwap, avg_price=avg_price):
            # Our own band (T3.0a S5), and an entry can always be refused: a book
            # whose vwap sits outside PERCENT_PRICE_BY_SIDE around the exchange
            # average is a corrupted snapshot, and paper equity is the lab's only
            # output (review of 2026-09-07, item 15).
            return self._no_fill(common, verdict.qty, "price_band", now)
        fee = taker_fee(
            fees, asset="base", base_qty=walk.filled_qty, gross=gross, vwap=vwap, policy=self.policy
        )
        return self._filled(
            common,
            walk,
            gross,
            vwap,
            book_verdict,
            now,
            fee=fee,
            net_base_delta=walk.filled_qty - fee.qty,
            net_quote_delta=-gross,
            remaining_cancelled=True,
            planned=order.entry_ref,
            side=OrderSide.BUY,
        )

    def submit_protection_exit(
        self,
        attempt: ExitAttempt,
        position_qty: Decimal,
        book: NormalizedOrderBook | None,
        last_trade: NormalizedTrade | None,
        filters: SpotFilters,
        fees: FeeSchedule,
        now: datetime,
        *,
        avg_price: Decimal | None = None,
        already_consumed: Sequence[LevelFill] = (),
        previous_book_sequence: int | None = None,
    ) -> ExecutionReport:
        """One attempt at a durable intention, which survives whatever it fails to sell."""
        recorded = self._replay(attempt.execution_key)
        if recorded is not None:
            return guard_replay(recorded, submitted_qty=attempt.qty)
        intent = attempt.intent
        common = attempt.report_identity(last_trade)
        if not intent.live:
            return self._no_fill(common, Decimal(0), "intent_terminal", now)
        usable, _ = usable_trade(last_trade, now=now, policy=self.policy.marking_policy)
        mark = mark_price(usable, avg_price, now=now, policy=self.policy)
        common |= reference_fields(usable, avg_price, now=now, policy=self.policy)
        wanted = min(attempt.qty, max(position_qty, Decimal(0)), intent.remaining_qty)
        if wanted <= 0:
            return self._no_fill(common, Decimal(0), "no_position_qty", now)
        verdict = filters.check_market_order(
            wanted, avg_price=avg_price, last_price=None if usable is None else usable.price
        )
        if not verdict.ok:
            reason = verdict.reason or "filter"
            if reason not in _MINIMUM_REASONS:
                # A missing average price does not *prove* the leftover is dust:
                # it proves we could not judge it. Calling it a residual would
                # retire a protection because a reference was late (Astra, T3.4
                # diff review, 4). The intention stays, degraded, with an alert.
                return self._no_fill(common, wanted, reason, now, degraded=True)
            leftover = residual_for(wanted, reason, mark, policy=self.policy)
            return self._no_fill(common, verdict.qty, reason, now, residual=leftover)
        market = None if intent.market is None else (intent.market.exchange, intent.market.symbol)
        book_verdict = eligible_for(
            self.policy,
            book,
            decision_at=attempt.decision_at,
            now=now,
            side=OrderSide.SELL,
            previous_sequence=previous_book_sequence,
            market=market,
        )
        if not book_verdict.eligible or book is None:
            return self._no_fill(common, verdict.qty, book_verdict.reason, now, degraded=True)
        walk = walk_book(book, verdict.qty, side=OrderSide.SELL, already_consumed=already_consumed)
        if walk.filled_qty <= 0:
            return self._no_fill(common, verdict.qty, "no_depth", now, degraded=True)
        gross, vwap = apply_model_slippage(walk, side=OrderSide.SELL, policy=self.policy)
        fee = taker_fee(
            fees,
            asset="quote",
            base_qty=walk.filled_qty,
            gross=gross,
            vwap=vwap,
            policy=self.policy,
        )
        left = intent.remaining_qty - walk.filled_qty
        leftover = None
        blocked = untradable_reason(left, filters, vwap or mark[0]) if left > 0 else None
        if blocked is not None:
            leftover = residual_for(left, blocked, vwap or mark, policy=self.policy)
        # The band never refuses a protection: a real 20 % crash puts the fill
        # under ask_multiplier_down exactly when the stop matters most, and
        # "travas nao podem impedir saidas de protecao" (directive, rule 3). It is
        # published with an alert instead (review of 2026-09-07, item 15).
        breached = price_band_breach(
            filters, side=OrderSide.SELL, fill_price=vwap, avg_price=avg_price
        )
        return self._filled(
            common,
            walk,
            gross,
            vwap,
            book_verdict,
            now,
            fee=fee,
            net_base_delta=-walk.filled_qty,
            net_quote_delta=gross - fee.qty,
            remaining_cancelled=False,
            planned=attempt.planned_price,
            side=OrderSide.SELL,
            residual=leftover,
            alert=breached,
            reason="price_band_breached" if breached else "",
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
        """Stop and target by the last valid spot trade — never a mark price."""
        return check_triggers(
            position,
            trades,
            now,
            policy=self.policy.marking_policy,
            last_accepted_trade_id=last_accepted_trade_id,
            tape_gap=tape_gap,
        )

    # ---------------------------------------------------------------- helpers

    def _replay(self, execution_key: str) -> ExecutionReport | None:
        """The recorded execution of this key, if there is one.

        Whether it is really a *replay* of the same order is
        :func:`~hunter_core.execution.idempotency.guard_replay`'s question."""
        return None if self.journal is None else self.journal.get(execution_key)

    def _record(self, report: ExecutionReport) -> ExecutionReport:
        if self.journal is not None:
            self.journal.record(report)
        return report

    def _filled(
        self,
        common: dict[str, Any],
        walk: BookWalk,
        gross: Decimal,
        vwap: Decimal,
        book_verdict: BookVerdict,
        now: datetime,
        *,
        planned: Decimal | None,
        side: OrderSide,
        **fields: Any,
    ) -> ExecutionReport:
        """The report of an attempt that met the book, with its whole provenance."""
        return self._record(
            ExecutionReport(
                status="filled" if walk.unfilled_qty == 0 else "partially_filled",
                mode=self.mode,
                requested_qty=walk.filled_qty + walk.unfilled_qty,
                filled_qty=walk.filled_qty,
                unfilled_qty=walk.unfilled_qty,
                levels=walk.levels,
                gross_quote=gross,
                vwap=vwap,
                vwap_before_adjustment=walk.vwap,
                model_adjustment_bps=self.policy.extra_slippage_bps,
                depth_exhausted=walk.depth_exhausted,
                book_sequence=book_verdict.sequence,
                book_received_at=book_verdict.received_at,
                eligible_at=common["decision_at"] + self.policy.latency,
                **policy_versions(self.policy, now),
                **slippage_vs_plan(planned, walk.filled_qty, gross, side=side, policy=self.policy),
                **common,
                **fields,
            )
        )

    def _no_fill(
        self,
        common: dict[str, Any],
        qty: Decimal,
        reason: str,
        now: datetime,
        *,
        degraded: bool = False,
        residual: Residual | None = None,
    ) -> ExecutionReport:
        """An attempt that produced nothing, and why.

        ``degraded`` is the protection case — no usable book, so the exit stays
        **pending** with an alert and the intention keeps the quantity. The
        refusal case is a filter or a book the entry could not use; for an entry
        the remainder is cancelled with it, because an entry is one attempt.
        """
        return self._record(
            ExecutionReport(
                status="pending_degraded" if degraded else "rejected",
                mode=self.mode,
                requested_qty=max(qty, Decimal(0)),
                unfilled_qty=max(qty, Decimal(0)),
                remaining_cancelled=not degraded and common["kind"] == "entry",
                residual=residual,
                degraded=degraded,
                alert=degraded,
                reason=reason,
                **policy_versions(self.policy, now),
                **common,
            )
        )
