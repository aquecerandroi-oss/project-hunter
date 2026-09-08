"""V10 — a degraded protection survives a restart with the remaining quantity.

**Objetivo (T3.29 item 3, from Astra's review of 2026-09-08, row "Proteção").**
V9 already proves that no usable book never fabricates a fill, and V6 step 5
proves a *partially filled* stop finishes after a restart. Neither one covers the
state the review named: the attempt ends ``pending_degraded`` while the position
stays exposed, the process dies with the backoff and the watermark in memory
only, and the intention has to come back from Postgres alone — for the
**remaining** quantity, and without selling one unit twice.

RISK_ENGINE.md §10 is the contract this refutes or confirms: *"cada tentativa
também termina, mas a intenção durável permanece para a quantidade
remanescente"*. The scenario it exists to prevent is a stop of ten units that
found four sellable, went degraded on the rest, and left six units unprotected
after a restart.

**The restart is the honest one** (§12 trap 7, and the same device V6 uses): a
fresh :class:`TriggerWatermarks` and a fresh :class:`DegradedRetries` on every
cycle call. Both are declared in-memory-only by ``triggering.py``, so a call that
carries nothing over from the previous one *is* what a new process starts with.
That is also why the backoff matters here: a degraded intention inside its
backoff is deliberately not retried, and a restart is precisely what clears it.

Nothing here sleeps and nothing reads a wall clock: every instant is an explicit
offset of the fixture's ``NOW``.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_execution_worker.market_data import SpotSnapshot
from hunter_execution_worker.triggering import DegradedRetries

from .conftest import (
    NOW,
    admit_entry,
    at,
    count_rows,
    liquidity_for,
    read_exit_intents,
    read_orders,
    read_positions,
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

ENTRY_REF = Decimal(100)
STOP = Decimal("97.5")
STOP_PRINT = Decimal(95)
NET_BASE = Decimal("18.499482")
"""18,518 x 0,999 — §0/V5's own number: a spot buy pays its fee in the coin."""


async def _open_a_position(factory: async_sessionmaker[AsyncSession], wallet: Wallet) -> Market:
    """One real entry through the real cycle — never a hand-written fill."""
    market = wallet.market("SOLUSDT")
    decision = await admit_entry(
        factory,
        wallet,
        market,
        now=NOW,
        marks={market.id: ENTRY_REF},
        liquidity=liquidity_for(market, as_of=NOW, last_price=ENTRY_REF),
    )
    assert decision.approved
    fill_at = at(seconds=1)
    outcomes = await run_entries(
        factory,
        wallet,
        static_data(
            market,
            SpotSnapshot(
                market=market.identity,
                book=spot_book(
                    market,
                    received_at=fill_at + timedelta(milliseconds=300),
                    bid=ENTRY_REF,
                    ask=ENTRY_REF,
                ),
                trades=(spot_trade(market, price=ENTRY_REF, ts=fill_at, trade_id=1),),
                avg_price=ENTRY_REF,
            ),
        ),
        now=fill_at + timedelta(seconds=1),
    )
    assert [o.status for o in outcomes] == ["filled"]
    return market


class TestADegradedProtectionComesBackForTheRemainderAndOnlyTheRemainder:
    """**O que refuta:**

    - an intention that ends anything but ``open`` while quantity is still
      owned, or one whose ``filled_qty`` does not match what really sold;
    - a restarted worker that re-sells the four units the first cycle already
      sold (the ledger would show more sold than the position ever held);
    - a second attempt reusing the first attempt's ``client_order_id``, which
      is what would make ``uq_orders_client_order_id`` swallow the recovery;
    - a degraded attempt that wrote a ``fills`` row for a book that did not
      exist.
    """

    async def test_the_remainder_survives_the_gap_and_the_restart(
        self, engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        market = await _open_a_position(factory, wallet)

        # --- cycle 1: the stop crosses and the book has only 4 of the units it
        # asks for. RISK_ENGINE.md §10's literal "um stop de 10 unidades
        # encontra 4 vendáveis", on this suite's own quantities.
        stop_at = at(minutes=1)
        partial_at = stop_at + timedelta(seconds=1)
        sold_first = Decimal(4)
        partial = await run_protection(
            factory,
            wallet,
            static_data(
                market,
                SpotSnapshot(
                    market=market.identity,
                    book=spot_book(
                        market,
                        received_at=stop_at + timedelta(milliseconds=300),
                        bid=STOP_PRINT,
                        ask=Decimal("95.05"),
                        qty=sold_first,
                    ),
                    trades=(spot_trade(market, price=STOP_PRINT, ts=stop_at, trade_id=2),),
                    avg_price=ENTRY_REF,
                ),
            ),
            now=partial_at,
        )
        assert [o.status for o in partial] == ["partially_filled"]
        assert (await read_positions(engine, wallet))[0].qty == NET_BASE - sold_first

        # --- cycle 2: the book is gone entirely. The attempt ends
        # ``pending_degraded``: no fill is fabricated, the intention keeps the
        # remaining quantity, and ``degraded_since`` starts running.
        gap_at = partial_at + timedelta(seconds=30)
        degraded = await run_protection(
            factory,
            wallet,
            static_data(
                market,
                SpotSnapshot(
                    market=market.identity,
                    book=None,
                    trades=(spot_trade(market, price=STOP_PRINT, ts=gap_at, trade_id=3),),
                    avg_price=ENTRY_REF,
                ),
            ),
            now=gap_at + timedelta(seconds=1),
            retries=DegradedRetries(),
        )
        assert [o.status for o in degraded] == ["pending_degraded"]
        intents = await read_exit_intents(engine, wallet)
        assert intents[0].state == "open"
        assert intents[0].filled_qty == sold_first
        assert intents[0].degraded_since is not None
        fills_before = await count_rows(engine, wallet, "fills")
        # The entry and the partial exit — the degraded attempt wrote none.
        assert fills_before == 2
        attempts_before = [order.client_order_id for order in await read_orders(engine, wallet)]

        # --- the restart. A brand-new ``DegradedRetries`` (and no watermarks):
        # a new process has neither the backoff nor the mark, and both losses
        # cause a re-evaluation, never a second sale.
        back_at = gap_at + timedelta(minutes=1)
        finished = await run_protection(
            factory,
            wallet,
            static_data(
                market,
                SpotSnapshot(
                    market=market.identity,
                    book=spot_book(
                        market,
                        received_at=back_at + timedelta(milliseconds=300),
                        bid=STOP_PRINT,
                        ask=Decimal("95.05"),
                    ),
                    trades=(spot_trade(market, price=STOP_PRINT, ts=back_at, trade_id=4),),
                    avg_price=ENTRY_REF,
                ),
            ),
            now=back_at + timedelta(seconds=1),
            retries=DegradedRetries(),
        )
        assert [o.status for o in finished] == ["filled"]

        positions = await read_positions(engine, wallet)
        after = await read_exit_intents(engine, wallet)
        orders = await read_orders(engine, wallet)
        attempts_after = [order.client_order_id for order in orders]

        # The remainder, and only the remainder: what the intention reports sold
        # is exactly what left the position, dust included.
        assert after[0].filled_qty == NET_BASE - positions[0].qty
        assert after[0].filled_qty > sold_first
        assert positions[0].status == "closing"  # dust, T3.5b — not an unprotected loss

        # No unit sold twice, and no attempt identity reused: three attempts,
        # three ``client_order_id``, one of them (the degraded one) with no fill.
        assert len(attempts_after) == len(set(attempts_after))
        assert attempts_after[: len(attempts_before)] == attempts_before
        sells = [order for order in orders if order.side == "sell"]
        assert sum((order.filled_qty for order in sells), Decimal(0)) == after[0].filled_qty
        assert await count_rows(engine, wallet, "fills") == fills_before + 1
