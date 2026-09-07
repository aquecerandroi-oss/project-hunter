"""V8 — a gap through the stop is published worse than planned, never corrected.

**Objetivo (spec V8):** an adverse gap produces a fill worse than the planned
stop, and the system never fabricates a perfect exit that did not happen —
``slippage_vs_plan_bps`` is published, positive (adverse) and never rewritten
back toward the plan.

Every number below is the ``.claude/state/t35-proof.md`` §3 reconciliation —
the real 30-minute proof of the ``execution-worker``, not a number invented
for this test: entry 18,518 @ 100,01, stop 97,5, gap to 95,00, taker fee 10
bps both sides, ``slippage_vs_plan_bps = 256,4102564100``,
``pnl = -96,28938018``, patrimônio final 19.903,708205.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_execution_worker.market_data import SpotSnapshot

from .conftest import (
    NOW,
    admit_entry,
    at,
    liquidity_for,
    mark_to_market,
    read_fills,
    read_positions,
    read_trades,
    run_entries,
    run_protection,
    spot_book,
    spot_trade,
    static_data,
)

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from .conftest import Market, Wallet

pytestmark = [pytest.mark.integration]

ENTRY_PRICE = Decimal("100.01")
STOP = Decimal("97.5")
GAP_PRICE = Decimal("95.00")
NET_BASE = Decimal("18.499482")
SOLD = Decimal("18.499")
DUST = NET_BASE - SOLD
ENTRY_FEE_QUOTE_EQUIVALENT = Decimal("1.85198518")
EXIT_FEE_QUOTE = Decimal("1.75740500")
SLIPPAGE_QUOTE = Decimal("46.2475")
SLIPPAGE_BPS = Decimal("256.41025641")
PNL = Decimal("-96.28938018")
CASH_AFTER = Decimal("19903.662415")
DUST_VALUE = Decimal("0.04579")
EQUITY_AFTER = Decimal("19903.708205")


async def _open_and_gap(
    factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> tuple[Market, datetime]:
    """Enter 18,518 @ 100,01, then gap straight through the 97,5 stop to 95,00.

    A single flat book level at each instant keeps every VWAP exact, so the
    only slippage this scenario produces is the gap itself — never the walk's
    own rounding.
    """
    market = wallet.market("SOLUSDT")
    # The decision is sized at the clean V1 geometry (entry_ref = market = 100,
    # qty = 18,518) — the same proposal ``t35-proof.md`` admitted. The fill
    # then meets a book at 100,01, a small, real difference between the
    # decision's reference and what the book actually offered a moment later.
    decision = await admit_entry(
        factory,
        wallet,
        market,
        now=NOW,
        marks={market.id: Decimal(100)},
        liquidity=liquidity_for(market, as_of=NOW, last_price=Decimal(100)),
    )
    assert decision.approved
    fill_at = at(seconds=1)
    entry_book_at = fill_at + timedelta(milliseconds=300)
    entries = await run_entries(
        factory,
        wallet,
        static_data(
            market,
            SpotSnapshot(
                market=market.identity,
                book=spot_book(market, received_at=entry_book_at, bid=ENTRY_PRICE, ask=ENTRY_PRICE),
                trades=(spot_trade(market, price=ENTRY_PRICE, ts=fill_at, trade_id=1),),
                avg_price=ENTRY_PRICE,
            ),
        ),
        now=fill_at + timedelta(seconds=1),
    )
    assert [o.status for o in entries] == ["filled"]

    # The gap: the next valid print is 95,00, straight past the 97,5 stop —
    # nothing trades in between (a real market gap, not a test-interpolated
    # price, spec §12 trap 3).
    gap_at = at(minutes=1)
    gap_book_at = gap_at + timedelta(milliseconds=300)
    cycle_at = gap_at + timedelta(seconds=1)
    outcomes = await run_protection(
        factory,
        wallet,
        static_data(
            market,
            SpotSnapshot(
                market=market.identity,
                book=spot_book(
                    market, received_at=gap_book_at, bid=GAP_PRICE, ask=GAP_PRICE + Decimal("0.05")
                ),
                trades=(spot_trade(market, price=GAP_PRICE, ts=gap_at, trade_id=2),),
                avg_price=ENTRY_PRICE,
            ),
        ),
        now=cycle_at,
    )
    assert [o.status for o in outcomes] == ["filled"]
    return market, cycle_at


class TestTheGapFillIsPublishedWorseThanPlannedAndNeverCorrected:
    """**O que refuta:** any code path that substitutes ``stop`` (97,5) for the
    real fill price to "honour" the plan; a negative ``slippage_vs_plan_bps``
    for a fill that is objectively worse; a fill price other than 95,00 for a
    single-level gapped book.
    """

    async def test_the_fill_lands_at_the_gap_price_not_the_stop(
        self, engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        _market, _cycle_at = await _open_and_gap(factory, wallet)

        fills = await read_fills(engine, wallet)
        assert len(fills) == 2  # entry, then the gapped exit
        exit_fill = fills[1]
        assert exit_fill.side == "sell"
        assert exit_fill.price == GAP_PRICE  # never 97,5, never anything interpolated
        assert exit_fill.qty == SOLD
        assert exit_fill.fee == EXIT_FEE_QUOTE
        assert exit_fill.fee_asset == "USDT"  # sell fee is quote-side (adapter.py)
        # Published, positive (adverse), to eight decimals before storage
        # rounds it to NUMERIC(28,10) — the two compare equal regardless.
        assert exit_fill.slippage_bps == SLIPPAGE_BPS
        assert exit_fill.slippage_bps > 0


class TestTheRealizedLossIsNotClampedToTheRiskBudget:
    """The directive is explicit that M3 does not promise "perda realizada
    limitada ao stop planejado" (``docs/plans/M3.md``) — a gap can and does
    realise more than the planned 0,25 % of equity, and that is not a bug.

    **O que refuta:** a ``trades.pnl`` that stops at the planned risk budget
    (49,9986 USDT, V1's own number) instead of the real, larger loss; any
    field that reports this as an error or a rejected fill.
    """

    async def test_the_trade_pnl_matches_the_proof_exactly_and_exceeds_the_planned_risk(
        self, engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        market, cycle_at = await _open_and_gap(factory, wallet)

        trades = await read_trades(engine, wallet)
        assert len(trades) == 1
        trade = trades[0]
        assert trade.entry_price == ENTRY_PRICE
        assert trade.exit_price == GAP_PRICE
        assert trade.qty == SOLD
        assert trade.fees == ENTRY_FEE_QUOTE_EQUIVALENT + EXIT_FEE_QUOTE
        assert trade.pnl == PNL
        planned_risk_quote = Decimal("49.9986")  # V1's own worked number, same market/geometry
        assert -trade.pnl > planned_risk_quote  # the loss is worse than the plan, not clamped

        positions = await read_positions(engine, wallet)
        assert len(positions) == 1
        assert positions[0].qty == DUST
        assert positions[0].status == "closing"  # dust, T3.5b — visible, never quietly settled

        build, _evaluation = await mark_to_market(
            engine, factory, wallet, marks={market.id: GAP_PRICE}, at_instant=cycle_at
        )
        assert build.cash == CASH_AFTER
        assert build.equity == EQUITY_AFTER
        assert build.equity == build.cash + build.exposure_notional
        assert build.exposure_notional == DUST * GAP_PRICE == DUST_VALUE
