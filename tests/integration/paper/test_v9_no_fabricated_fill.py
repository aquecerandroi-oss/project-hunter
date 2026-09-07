"""V9 — no usable book never fabricates a fill.

**Objetivo (spec V9):** without an eligible book, a protection exit never
invents a fill — it stays ``pending_degraded``, ``degraded=True``,
``alert=True``, and the durable intention stays ``open``, never ``fulfilled``
by a candle or a stale quote.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_core.domain.enums import ExecutionMode, MarketType, OrderSide, Timeframe
from hunter_core.domain.market import NormalizedCandle
from hunter_core.domain.types import uuid7
from hunter_core.execution.adapter import ExecutionReport
from hunter_core.execution.paper import PaperExecutionAdapter
from hunter_core.execution.triggers import ProtectedPosition
from hunter_execution_worker.market_data import SpotSnapshot

from .conftest import (
    NOW,
    admit_entry,
    at,
    count_rows,
    liquidity_for,
    read_exit_intents,
    read_orders,
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

ENTRY_PRICE = Decimal(100)
STOP = Decimal("97.5")
GAP_PRICE = Decimal(95)


async def _open_a_position(factory: async_sessionmaker[AsyncSession], wallet: Wallet) -> Market:
    market = wallet.market("SOLUSDT")
    decision = await admit_entry(
        factory,
        wallet,
        market,
        now=NOW,
        marks={market.id: ENTRY_PRICE},
        liquidity=liquidity_for(market, as_of=NOW, last_price=ENTRY_PRICE),
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
                book=spot_book(market, received_at=book_at, bid=ENTRY_PRICE, ask=ENTRY_PRICE),
                trades=(spot_trade(market, price=ENTRY_PRICE, ts=fill_at, trade_id=1),),
                avg_price=ENTRY_PRICE,
            ),
        ),
        now=fill_at + timedelta(seconds=1),
    )
    assert [o.status for o in outcomes] == ["filled"]
    return market


class TestNoUsableBookNeverFabricatesAFill:
    """**O que refuta:** any ``fills`` row written when ``book=None``; a
    status other than ``pending_degraded``; an intention that leaves ``open``
    without ``degraded=True``.
    """

    async def test_a_stop_crossing_with_no_book_writes_an_order_and_no_fill(
        self, engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        market = await _open_a_position(factory, wallet)
        stop_at = at(minutes=1)
        cycle_at = stop_at + timedelta(seconds=1)
        outcomes = await run_protection(
            factory,
            wallet,
            static_data(
                market,
                SpotSnapshot(
                    market=market.identity,
                    book=None,
                    trades=(spot_trade(market, price=GAP_PRICE, ts=stop_at, trade_id=2),),
                    avg_price=ENTRY_PRICE,
                ),
            ),
            now=cycle_at,
        )
        assert [o.status for o in outcomes] == ["pending_degraded"]

        assert await count_rows(engine, wallet, "fills") == 1  # the entry only, never the exit
        assert await count_rows(engine, wallet, "orders") == 2  # entry + the degraded attempt
        orders = await read_orders(engine, wallet)
        degraded_order = orders[-1]
        assert degraded_order.side == "sell"
        assert degraded_order.filled_qty == Decimal(0)

        intents = await read_exit_intents(engine, wallet)
        assert intents[0].state == "open"
        assert intents[0].filled_qty == Decimal(0)
        assert intents[0].degraded_since is not None


class TestTheValidatorRefusesToRepresentAFabricatedFill:
    """The impossibility lives in the constructor, not in a check somebody
    could forget to call (``adapter.py:183-201``).

    **O que refuta:** any successful construction of an
    :class:`ExecutionReport` claiming a fill under a status the schema defines
    as fill-less.
    """

    def test_pending_degraded_with_a_positive_filled_qty_cannot_be_built(self) -> None:
        from hunter_core.execution.adapter import LevelFill

        with pytest.raises(ValueError, match="cannot carry a fill"):
            ExecutionReport(
                kind="exit",
                status="pending_degraded",
                mode=ExecutionMode.PAPER,
                execution_key="exit:test",
                client_order_id="exit:test",
                side=OrderSide.SELL,
                requested_qty=Decimal(1),
                filled_qty=Decimal(1),
                # The levels sum to the claimed fill on purpose: this test
                # isolates the *second* guard (a status that may not carry a
                # fill at all), not the first one (V9's other test).
                levels=(LevelFill(price=Decimal(100), qty=Decimal(1)),),
                degraded=True,
                alert=True,
            )

    def test_filled_quantity_must_equal_the_book_levels_actually_consumed(self) -> None:
        from hunter_core.execution.adapter import LevelFill

        with pytest.raises(ValueError, match="no fill is ever fabricated"):
            ExecutionReport(
                kind="exit",
                status="filled",
                mode=ExecutionMode.PAPER,
                execution_key="exit:test",
                client_order_id="exit:test",
                side=OrderSide.SELL,
                requested_qty=Decimal(5),
                filled_qty=Decimal(5),
                levels=(LevelFill(price=Decimal(100), qty=Decimal(3)),),  # only 3 walked, not 5
            )


class TestACandleNeverSuppliesARetroactiveFill:
    """A ``NormalizedCandle`` whose ``low`` sits below the stop is not a trade
    the trigger reader can use — it has no ``.ts``/``.trade_id``/``.price`` at
    all, so handing one to :meth:`PaperExecutionAdapter.check_triggers`
    crashes rather than silently reading it as a print that crossed the stop.

    **O que refuta:** any successful, "triggered" evaluation built from a
    candle; a code path that reads ``candle.low`` as if it were a trade price.
    """

    def test_a_candle_crashes_the_trigger_reader_instead_of_firing_it(self) -> None:
        candle = NormalizedCandle(
            exchange="binance",
            symbol="SOLUSDT",
            market_type=MarketType.SPOT,
            timeframe=Timeframe.M1,
            received_at=datetime(2026, 9, 6, 18, 31, tzinfo=UTC),
            open_time=datetime(2026, 9, 6, 18, 30, tzinfo=UTC),
            close_time=datetime(2026, 9, 6, 18, 31, tzinfo=UTC),
            open=Decimal(100),
            high=Decimal(100),
            low=Decimal(96),  # below the 97,5 stop
            close=Decimal(98),
            volume=Decimal(1000),
            is_final=True,
        )
        position = ProtectedPosition(
            position_id=uuid7(), qty=Decimal(10), stop_price=STOP, target_prices=()
        )
        with pytest.raises(AttributeError):
            PaperExecutionAdapter().check_triggers(
                position,
                [candle],  # type: ignore[list-item]  # exactly the point: this is not a trade
                datetime(2026, 9, 6, 18, 32, tzinfo=UTC),
            )


class TestARestoredBookGetsANewAttemptForTheSameIntention:
    """Step 4: the book reconnects, and the same live intention gets a
    **new** attempt with its own identity — never a second consumption of
    what the degraded attempt never actually took (it took nothing).

    **O que refuta:** the second attempt reusing the first's
    ``client_order_id``; the intention's ``filled_qty`` counting the degraded
    attempt as if it had sold anything.
    """

    async def test_the_reconnect_produces_a_fresh_attempt_that_fills(
        self, engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        market = await _open_a_position(factory, wallet)
        stop_at = at(minutes=1)
        degraded_cycle_at = stop_at + timedelta(seconds=1)
        degraded = await run_protection(
            factory,
            wallet,
            static_data(
                market,
                SpotSnapshot(
                    market=market.identity,
                    book=None,
                    trades=(spot_trade(market, price=GAP_PRICE, ts=stop_at, trade_id=2),),
                    avg_price=ENTRY_PRICE,
                ),
            ),
            now=degraded_cycle_at,
        )
        assert [o.status for o in degraded] == ["pending_degraded"]
        first_order = (await read_orders(engine, wallet))[-1].client_order_id

        later = degraded_cycle_at + timedelta(seconds=5)
        later_book_at = later + timedelta(milliseconds=300)
        later_cycle_at = later + timedelta(seconds=1)
        recovered = await run_protection(
            factory,
            wallet,
            static_data(
                market,
                SpotSnapshot(
                    market=market.identity,
                    book=spot_book(
                        market,
                        received_at=later_book_at,
                        bid=GAP_PRICE,
                        ask=GAP_PRICE + Decimal("0.05"),
                    ),
                    trades=(spot_trade(market, price=GAP_PRICE, ts=later, trade_id=3),),
                    avg_price=ENTRY_PRICE,
                ),
            ),
            now=later_cycle_at,
        )
        assert [o.status for o in recovered] == ["filled"]

        second_order = (await read_orders(engine, wallet))[-1].client_order_id
        assert second_order != first_order

        intents = await read_exit_intents(engine, wallet)
        # Everything sold came from the one real attempt — the degraded one
        # contributed exactly zero, never double-counted.
        assert intents[0].filled_qty == Decimal("18.499")
        assert await count_rows(engine, wallet, "fills") == 2  # entry + the one real exit fill
