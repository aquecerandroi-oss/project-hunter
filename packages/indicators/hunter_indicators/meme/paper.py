"""A paper wallet that trades one bonding curve — no IO, no clock, no order.

The simulator the T4.4 doctrine asks for before any key exists: a SOL balance
with a cap, positions per mint, a ledger of every event *including every
refusal*, and a valuation that is the honest one — what a full sell would yield
**now**, fees included, not the marginal price times the tokens held.

Two decisions worth reading before using it:

1. **A fill is priced against reserves observed strictly after the intent.**
   :meth:`PaperCurveWallet.buy` and :meth:`~PaperCurveWallet.sell` take both
   ``intent_ts`` (when we decided) and ``ts`` (when the reserves being priced
   were observed) and refuse ``fill_not_after_intent`` when the second is not
   after the first. Concurrency slippage is then whatever the next snapshot says
   it is — never an assumption that our order hit the last seen price.
2. **The loss latch blocks new risk, never an exit.** Crossing
   ``daily_loss_cap_sol`` within a UTC day latches the wallet: buys are refused
   by name until :meth:`~PaperCurveWallet.resume` is called (the OWNER's act in
   the doctrine). The booked loss is not erased by the resume; the cap restarts
   counting from there, so a resumed wallet does not re-latch for a loss it has
   already declared.

Value objects live in :mod:`.models`, the refusal vocabulary in :mod:`.guards`;
both are re-exported here, because "the paper wallet" is one idea for a caller.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from decimal import Decimal, localcontext

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.curve import BuyQuote, CurveReserves, quote_buy, quote_sell
from hunter_indicators.meme.guards import refuse_buy, refuse_sell
from hunter_indicators.meme.models import (
    Fill,
    LedgerEvent,
    LedgerKind,
    PaperPosition,
    PaperWalletLimits,
    accepted_fill,
    refused_fill,
    require_utc,
    utc_day,
)
from hunter_indicators.meme.valuation import Equity, equity_sol, position_mark_sol

__all__ = [
    "Fill",
    "LedgerEvent",
    "LedgerKind",
    "PaperCurveWallet",
    "PaperPosition",
    "PaperWalletLimits",
]

ZERO = Decimal(0)


class PaperCurveWallet:
    """A paper SOL wallet trading pump.fun curves. Mutable by design, pure by contract."""

    def __init__(
        self, *, limits: PaperWalletLimits, balance_sol: Decimal, opened_at: datetime
    ) -> None:
        require_utc(opened_at, "opened_at")
        if balance_sol <= 0:
            raise ValueError("balance_sol must be positive")
        if balance_sol > limits.max_balance_sol:
            raise ValueError("balance_sol above max_balance_sol")
        self._limits = limits
        self._balance = balance_sol  # the opening balance survives as ledger[0].balance_after
        self._positions: dict[str, PaperPosition] = {}
        self._realized_by_day: dict[str, Decimal] = {}
        self._latch_baseline: dict[str, Decimal] = {}
        self._halted_reason: str | None = None
        self._ledger: list[LedgerEvent] = []
        self._record(LedgerKind.OPEN, ts=opened_at, mint=None, sol_delta=ZERO, tokens=ZERO)

    # ---- reading -----------------------------------------------------------

    @property
    def limits(self) -> PaperWalletLimits:
        return self._limits

    @property
    def balance_sol(self) -> Decimal:
        return self._balance

    @property
    def ledger(self) -> tuple[LedgerEvent, ...]:
        return tuple(self._ledger)

    @property
    def positions(self) -> Mapping[str, PaperPosition]:
        return dict(self._positions)

    @property
    def halted_reason(self) -> str | None:
        return self._halted_reason

    @property
    def realized_pnl_sol(self) -> Decimal:
        return sum(self._realized_by_day.values(), start=ZERO)

    @property
    def realized_pnl_by_day(self) -> Mapping[str, Decimal]:
        """Realized PnL keyed by UTC day — the block EXP-M1 resamples."""
        return dict(self._realized_by_day)

    def position(self, mint: str) -> PaperPosition | None:
        return self._positions.get(mint)

    def mark_to_curve(self, mint: str, reserves: CurveReserves) -> Decimal | None:
        """SOL a full sell of the position would net **now**, fees included."""
        position = self._positions.get(mint)
        if position is None:
            return None
        return position_mark_sol(position, reserves, self._limits.fee_pct)

    def equity(self, reserves_by_mint: Mapping[str, CurveReserves]) -> Equity:
        """Balance plus every mark, with the unpriceable positions **named** (§10.6)."""
        return equity_sol(self._balance, self._positions, reserves_by_mint, self._limits.fee_pct)

    def unrealized_pnl_sol(self, mint: str, reserves: CurveReserves) -> Decimal | None:
        """Mark minus everything paid. Negative right after entry, and that is the point."""
        position = self._positions.get(mint)
        mark = self.mark_to_curve(mint, reserves)
        if position is None or mark is None:
            return None
        with localcontext(CONTEXT):
            return mark - position.cost_basis_sol

    def record_mark(self, mint: str, reserves: CurveReserves, *, ts: datetime) -> Decimal | None:
        """Observe a mark and raise the position's peak; the trailing rule reads that peak."""
        require_utc(ts, "ts")
        position = self._positions.get(mint)
        mark = self.mark_to_curve(mint, reserves)
        if position is None or mark is None:
            return None
        if mark > position.peak_mark_sol:
            self._positions[mint] = replace(position, peak_mark_sol=mark)
        return mark

    # ---- trading -----------------------------------------------------------

    def buy(
        self,
        mint: str,
        sol: Decimal,
        reserves_at: CurveReserves,
        *,
        ts: datetime,
        intent_ts: datetime,
        priority_fee_sol: Decimal = ZERO,
    ) -> Fill:
        """Spend ``sol`` (plus ``priority_fee_sol``) against the reserves observed at ``ts``."""
        require_utc(ts, "ts")
        require_utc(intent_ts, "intent_ts")
        reason = refuse_buy(
            limits=self._limits,
            balance_sol=self._balance,
            positions=self._positions,
            halted_reason=self._halted_reason,
            mint=mint,
            sol=sol,
            reserves=reserves_at,
            ts=ts,
            intent_ts=intent_ts,
            priority_fee_sol=priority_fee_sol,
        )
        if reason is not None:
            return self._refused(mint, ts, reason)
        quote = quote_buy(reserves_at, sol, self._limits.fee_pct)
        with localcontext(CONTEXT):
            spent = quote.total_sol + priority_fee_sol
            self._balance -= spent
            self._positions[mint] = self._merge_position(
                mint, spent, quote, priority_fee_sol, reserves_at, ts
            )
            event = self._record(
                LedgerKind.BUY,
                ts=ts,
                mint=mint,
                sol_delta=-spent,
                tokens=quote.tokens,
                fee_sol=quote.fee_sol,
                priority_fee_sol=priority_fee_sol,
                marginal_price=quote.marginal_price_after_sol,
            )
        return accepted_fill(
            event, mint=mint, tokens=quote.tokens, reserves_after=quote.reserves_after
        )

    def sell(
        self,
        mint: str,
        tokens: Decimal,
        reserves_at: CurveReserves,
        *,
        ts: datetime,
        intent_ts: datetime,
        priority_fee_sol: Decimal = ZERO,
    ) -> Fill:
        """Sell ``tokens`` against the reserves observed at ``ts``. Never blocked by the latch."""
        require_utc(ts, "ts")
        require_utc(intent_ts, "intent_ts")
        position = self._positions.get(mint)
        reason = refuse_sell(position=position, tokens=tokens, ts=ts, intent_ts=intent_ts)
        if reason is not None or position is None:
            return self._refused(mint, ts, reason or "no_position")
        quote = quote_sell(reserves_at, tokens, self._limits.fee_pct)
        with localcontext(CONTEXT):
            share = tokens / position.tokens
            released = position.cost_basis_sol * share
            realized = quote.net_sol - released - priority_fee_sol
            self._balance += quote.net_sol - priority_fee_sol
            self._reduce_position(position, tokens, released, share)
            event = self._record(
                LedgerKind.SELL,
                ts=ts,
                mint=mint,
                sol_delta=quote.net_sol - priority_fee_sol,
                tokens=-tokens,
                fee_sol=quote.fee_sol,
                priority_fee_sol=priority_fee_sol,
                marginal_price=quote.marginal_price_after_sol,
                realized=realized,
            )
            self._book_realized(ts, realized)
        return accepted_fill(event, mint=mint, tokens=tokens, reserves_after=quote.reserves_after)

    def resume(self, *, ts: datetime, note: str) -> None:
        """Clear the latch explicitly. The loss stays booked; the cap restarts from here."""
        require_utc(ts, "ts")
        self._halted_reason = None
        day = utc_day(ts)
        self._latch_baseline[day] = self._realized_by_day.get(day, ZERO)
        self._record(LedgerKind.RESUMED, ts=ts, mint=None, sol_delta=ZERO, tokens=ZERO, reason=note)

    # ---- bookkeeping -------------------------------------------------------

    def _merge_position(
        self,
        mint: str,
        spent: Decimal,
        quote: BuyQuote,
        priority_fee_sol: Decimal,
        reserves_at: CurveReserves,
        ts: datetime,
    ) -> PaperPosition:
        held = self._positions.get(mint)
        if held is None:
            mark = quote_sell(quote.reserves_after, quote.tokens, self._limits.fee_pct).net_sol
            return PaperPosition(
                mint=mint,
                tokens=quote.tokens,
                cost_basis_sol=spent,
                curve_cost_sol=quote.curve_cost_sol,
                fees_sol=quote.fee_sol,
                priority_fees_sol=priority_fee_sol,
                entry_reserves=reserves_at,
                entry_ts=ts,
                peak_mark_sol=mark,
            )
        return replace(
            held,
            tokens=held.tokens + quote.tokens,
            cost_basis_sol=held.cost_basis_sol + spent,
            curve_cost_sol=held.curve_cost_sol + quote.curve_cost_sol,
            fees_sol=held.fees_sol + quote.fee_sol,
            priority_fees_sol=held.priority_fees_sol + priority_fee_sol,
        )

    def _reduce_position(
        self, position: PaperPosition, tokens: Decimal, released: Decimal, share: Decimal
    ) -> None:
        remaining = position.tokens - tokens
        if remaining <= 0:
            del self._positions[position.mint]
            return
        keep = Decimal(1) - share
        self._positions[position.mint] = replace(
            position,
            tokens=remaining,
            cost_basis_sol=position.cost_basis_sol - released,
            curve_cost_sol=position.curve_cost_sol * keep,
            fees_sol=position.fees_sol * keep,
            priority_fees_sol=position.priority_fees_sol * keep,
        )

    def _book_realized(self, ts: datetime, realized: Decimal) -> None:
        day = utc_day(ts)
        with localcontext(CONTEXT):
            total = self._realized_by_day.get(day, ZERO) + realized
            self._realized_by_day[day] = total
            baseline = self._latch_baseline.get(day, ZERO)
            if total - baseline <= -self._limits.daily_loss_cap_sol:
                self._halted_reason = "daily_loss_cap_latched"
                self._record(
                    LedgerKind.HALTED,
                    ts=ts,
                    mint=None,
                    sol_delta=ZERO,
                    tokens=ZERO,
                    reason=self._halted_reason,
                )

    def _refused(self, mint: str, ts: datetime, reason: str) -> Fill:
        event = self._record(
            LedgerKind.REFUSED, ts=ts, mint=mint, sol_delta=ZERO, tokens=ZERO, reason=reason
        )
        return refused_fill(event, mint=mint)

    def _record(
        self,
        kind: LedgerKind,
        *,
        ts: datetime,
        mint: str | None,
        sol_delta: Decimal,
        tokens: Decimal,
        fee_sol: Decimal = ZERO,
        priority_fee_sol: Decimal = ZERO,
        reason: str | None = None,
        marginal_price: Decimal | None = None,
        realized: Decimal | None = None,
    ) -> LedgerEvent:
        event = LedgerEvent(
            seq=len(self._ledger),
            ts=ts,
            kind=kind,
            mint=mint,
            sol_delta=sol_delta,
            tokens_delta=tokens,
            fee_sol=fee_sol,
            priority_fee_sol=priority_fee_sol,
            balance_after=self._balance,
            reason=reason,
            marginal_price_sol=marginal_price,
            realized_pnl_sol=realized,
        )
        self._ledger.append(event)
        return event
