"""V5 — balances, fees and PnL reconciliation, fill by fill, against the §0 wallet.

**Objetivo (spec V5):** ``equity = cash + Σ valor_de_mercado(posições)`` never
diverges by more than the declared rounding error, and the base-asset fee
reduces exactly the sellable quantity — never the cash (Risk Engine and
execution use different currencies for the fee by design,
``.claude/state/notes-T3.0a.md`` §6 and ``adapter.py:91-105``).

Every number below is worked in ``.claude/state/spec-T3.9-verificacoes.md`` §V5
and is reproduced here from the persisted path, not trusted from the note.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from hunter_core.portfolio.state import PortfolioStateBuild
from hunter_execution_worker.market_data import SpotSnapshot

from .conftest import (
    CREDITED,
    NOW,
    admit_entry,
    at,
    liquidity_for,
    open_fresh_wallet,
    read_fills,
    read_positions,
    read_state,
    run_entries,
    run_protection,
    spot_book,
    spot_trade,
    static_data,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from .conftest import Market, Wallet

pytestmark = [pytest.mark.integration]
"""``asyncio_mode = "auto"`` (pyproject.toml) runs every ``async def`` test
without a marker; the property test below is a plain ``def`` (Hypothesis owns
its own loop per example, see its docstring), so an explicit ``asyncio`` mark
here would warn on exactly that one test."""

QTY = Decimal("18.518")
PRICE = Decimal(100)
GROSS = Decimal("1851.800")
FEE_RATE = Decimal("0.0010")
FEE_QTY = Decimal("0.0185180000")
NET_BASE = Decimal("18.499482")
CASH_AFTER = Decimal("18148.2000000000")
EQUITY_AT_MARK_100 = Decimal("19998.1482000000")
EQUITY_AT_MARK_101 = Decimal("20016.6476820000")


def _credited_loss(build: PortfolioStateBuild) -> Decimal:
    """How much of the opening's 20.000,0000000000 the wallet no longer shows."""
    return CREDITED - build.equity


async def _buy_18518_at_100(factory: async_sessionmaker[AsyncSession], wallet: Wallet) -> Market:
    """Fill the V1 proposal (18,518 @ 100) through the real entry cycle.

    A single flat book level at exactly 100 keeps the VWAP exact — the walk
    never slips, so the gross the ledger books is the textbook 1.851,800 the
    spec works with, and every rounding this test finds is the fee's, not the
    book's.
    """
    market = wallet.market("SOLUSDT")
    decision = await admit_entry(
        factory,
        wallet,
        market,
        now=NOW,
        marks={market.id: PRICE},
        liquidity=liquidity_for(market, as_of=NOW, last_price=PRICE),
    )
    assert decision.approved
    fill_at = at(seconds=1)
    book_at = fill_at + timedelta(milliseconds=300)
    outcomes = await run_entries(
        factory,
        wallet,
        static_data(
            market,
            SpotSnapshot(
                market=market.identity,
                book=spot_book(market, received_at=book_at, bid=PRICE, ask=PRICE),
                trades=(spot_trade(market, price=PRICE, ts=fill_at, trade_id=1),),
                avg_price=PRICE,
            ),
        ),
        now=fill_at + timedelta(seconds=1),
    )
    assert [o.status for o in outcomes] == ["filled"]
    return market


class TestOneFillReconciledExactly:
    """**O que refuta:** ``equity`` diverging from ``cash + Σ posições`` by more
    than the declared rounding (here, zero — a single-level walk books exact);
    the fee debiting cash in addition to the quantity (double charge); the
    marked-to-100 equity dropping by anything other than the fee's own quote
    value.
    """

    async def test_the_fill_debits_cash_by_the_gross_and_the_quantity_by_the_fee(
        self,
        engine: AsyncEngine,
        factory: async_sessionmaker[AsyncSession],
        wallet: Wallet,
    ) -> None:
        market = await _buy_18518_at_100(factory, wallet)

        fills = await read_fills(engine, wallet)
        assert len(fills) == 1
        fill = fills[0]
        assert fill.qty == QTY
        assert fill.price == PRICE
        assert fill.fee == FEE_QTY
        assert fill.fee_asset == market.base

        positions = await read_positions(engine, wallet)
        assert len(positions) == 1
        assert positions[0].qty == NET_BASE  # qty − fee, never the gross

        build = await read_state(
            factory, wallet, marks={market.id: PRICE}, at_instant=at(seconds=2)
        )
        assert build.cash == CASH_AFTER
        # equity = cash + Σ (qty × mark) — the identity itself, read from the
        # persisted state, not recomputed by this test with its own formula.
        assert build.equity == build.cash + build.exposure_notional
        assert build.exposure_notional == NET_BASE * PRICE
        assert build.equity == EQUITY_AT_MARK_100
        # The only loss from opening is the fee, in quote terms — nothing else
        # is silently rounded away.
        assert _credited_loss(build) == FEE_QTY * PRICE


class TestThePriceMoveAndTheFeeAreNeverConfused:
    """Step 3 of V5: mark at 101 and confirm the unrealised gain is separate
    from the fee already paid at entry — the two never collapse into one
    number that hides which part is cost and which part is market movement.

    **O que refuta:** an equity gain at mark 101 that is not
    ``(101 − 100) × net_qty`` net of the entry fee; a ``fee.quote_equivalent``
    that gets booked a second time into ``net_quote_delta`` (``adapter.py``'s
    own warning: "booking it as well would charge the trade twice").
    """

    async def test_marking_at_101_shows_price_gain_net_of_the_entry_fee_only(
        self,
        engine: AsyncEngine,
        factory: async_sessionmaker[AsyncSession],
        wallet: Wallet,
    ) -> None:
        market = await _buy_18518_at_100(factory, wallet)
        higher = Decimal(101)

        build = await read_state(
            factory, wallet, marks={market.id: higher}, at_instant=at(seconds=2)
        )
        assert build.cash == CASH_AFTER  # marking never touches cash
        assert build.exposure_notional == NET_BASE * higher
        assert build.equity == build.cash + build.exposure_notional
        assert build.equity == EQUITY_AT_MARK_101

        price_gain = NET_BASE * (higher - PRICE)
        entry_fee_quote = FEE_QTY * PRICE
        assert (build.equity - Decimal("20000.0000000000")) == price_gain - entry_fee_quote


@settings(
    max_examples=8,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(
    depths=st.lists(
        st.integers(min_value=1, max_value=17),  # in thousandths of a unit (step_size = 0,001)
        min_size=1,
        max_size=3,
    ),
    price_offsets=st.lists(st.integers(min_value=0, max_value=5), min_size=1, max_size=3),
)
def test_v5_property_equity_always_equals_cash_plus_marked_positions(
    paper_db_url: str,
    depths: list[int],
    price_offsets: list[int],
) -> None:
    """V5 step 4 (Hypothesis): for an arbitrary sequence of partial exits at
    varying prices, ``equity`` read back from Postgres is **always**
    ``cash + Σ qty × mark`` — the same invariant ``hunter_risk``'s
    ``test_properties.py`` already proves for sizing, extended here to the
    ledger, which is different code (``hunter_core.portfolio.state``).

    Every generated price stays below the 97,5 stop (94,5-95,0) so every
    example produces a real crossing and a real partial fill; only the book's
    depth (``depths``, in thousandths of a unit) varies how much of the
    remaining position each cycle's walk can actually reach — the same
    mechanism ``test_restart_recovery.py`` uses for a single shallow fill,
    repeated here an arbitrary number of times.

    Each example opens a **fresh** wallet on a **fresh** engine, disposed at
    the end of the example: ``engine``/``factory`` are ``pytest_asyncio``
    fixtures bound to the fixture loop, and ``asyncio.run`` below opens a new
    one per Hypothesis example — reusing a pool across the two produced
    ``asyncpg`` "another operation is in progress" errors the first time this
    property was written with the shared fixtures. ``paper_db_url`` is a plain
    string, safe to reuse across loops.

    **O que refuta:** any generated sequence where the recomputed equity
    diverges from the incrementally-maintained one by so much as one
    ``NUMERIC(28,10)`` unit.
    """

    async def scenario() -> None:
        from sqlalchemy.ext.asyncio import create_async_engine

        from hunter_core.db.session import create_session_factory

        fresh_engine = create_async_engine(paper_db_url, connect_args={"statement_cache_size": 0})
        try:
            fresh_factory = create_session_factory(fresh_engine)
            wallet = await open_fresh_wallet(fresh_engine, fresh_factory)
            market = await _buy_18518_at_100(fresh_factory, wallet)
            remaining = NET_BASE
            cursor = at(minutes=1)
            trade_id = 100
            for depth_thousandths, offset in zip(depths, price_offsets, strict=False):
                if remaining <= 0:
                    break
                depth = min(Decimal(depth_thousandths) / Decimal(1000), remaining)
                depth = (depth / Decimal("0.001")).to_integral_value() * Decimal("0.001")
                if depth <= 0:
                    continue
                price = Decimal(95) - Decimal(offset) * Decimal("0.1")  # below the 97,5 stop
                fire_at = cursor
                book_at = fire_at + timedelta(milliseconds=300)
                cycle_at = fire_at + timedelta(seconds=1)
                trade_id += 1
                await run_protection(
                    fresh_factory,
                    wallet,
                    static_data(
                        market,
                        SpotSnapshot(
                            market=market.identity,
                            book=spot_book(
                                market,
                                received_at=book_at,
                                bid=price,
                                ask=price + Decimal("0.05"),
                                qty=depth,
                            ),
                            trades=(
                                spot_trade(market, price=price, ts=fire_at, trade_id=trade_id),
                            ),
                            avg_price=PRICE,
                        ),
                    ),
                    now=cycle_at,
                )
                build = await read_state(
                    fresh_factory, wallet, marks={market.id: price}, at_instant=cycle_at
                )
                assert build.equity == build.cash + build.exposure_notional
                positions = await read_positions(fresh_engine, wallet)
                live = [p for p in positions if p.status != "closed"]
                remaining = live[0].qty if live else Decimal(0)
                cursor = cycle_at + timedelta(minutes=1)
        finally:
            await fresh_engine.dispose()

    asyncio.run(scenario())
