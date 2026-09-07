"""V4 — concurrent orders and duplicate fills, against the §0 wallet.

**Objetivo (spec V4):** two concurrent fills of the same intention never sell
or buy the same unit twice, and a redelivered fill event is absorbed without a
second effect.

**O que refuta cada teste** is named in its own docstring; the shared
refutation across the file is spec V4's list: the sum sold exceeding the
position; a replay creating a second ``fills``/``orders`` row or moving cash a
second time; a competing protection forced to ``fulfilled`` with a quantity it
never actually sold; two real sessions each seeing "N vendável" and together
selling more than the position ever held.

Two real ``AsyncSession``/connections are used wherever "concurrent" is the
claim (§12 trap 8: two tasks on one session serialise inside the driver and
prove nothing about a Postgres lock) — never ``asyncio.gather`` over one
session for the *database* work, only for two independently-opened ones.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import ExitIntentState, ExitReason
from hunter_core.execution.intents import ExitAttempt
from hunter_core.execution.paper import PaperExecutionAdapter
from hunter_execution_worker.apply_exit import apply_exit
from hunter_execution_worker.intents_repo import live_intents
from hunter_execution_worker.market_data import SpotSnapshot
from hunter_execution_worker.positions import load_open_positions
from hunter_execution_worker.reference import load_market

from .conftest import (
    NOW,
    at,
    count_rows,
    insert_intent_directly,
    market_reference,
    open_position_directly,
    read_exit_intents,
    read_positions,
    run_protection,
    spot_book,
    spot_trade,
    static_data,
    sum_sold,
    wallet_ref,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from .conftest import Market, Wallet

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

STOP = Decimal("97.5")
TARGET_TRIGGER = Decimal("105")
POSITION_QTY = Decimal(10)
ENTRY_PRICE = Decimal(100)
WORKER_ROLE = "hunter_worker"


async def _position_of_ten(
    factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> tuple[Market, uuid.UUID]:
    """Ten whole units, a stop for all of them, and a target for six.

    Written with the real production writers
    (``hunter_execution_worker.positions.open_position``,
    ``...intents_repo.insert_intent``) rather than through a fill: V4 is about
    what *two live protections* do to one position, not about the fee
    arithmetic of getting there — that is V5's job, and reusing its 18,518 @
    100,01 → 18,499482 net here would just be noise around this test's own
    number. The market is still the real §0 SOL (``step_size = 0,001``,
    ``min_notional = 5``), read back from the same row the worker reads.
    """
    market = wallet.market("SOLUSDT")
    position_id = await open_position_directly(
        factory,
        wallet,
        market,
        qty=POSITION_QTY,
        entry_price=ENTRY_PRICE,
        stop_price=STOP,
        now=NOW,
    )
    await insert_intent_directly(
        factory,
        wallet,
        market,
        position_id=position_id,
        protection_key="stop",
        intended_qty=POSITION_QTY,
        trigger_price=STOP,
        now=NOW,
        reason=ExitReason.STOP,
    )
    await insert_intent_directly(
        factory,
        wallet,
        market,
        position_id=position_id,
        protection_key="target:1",
        intended_qty=Decimal(6),
        trigger_price=TARGET_TRIGGER,
        now=NOW,
        reason=ExitReason.TARGET,
    )
    return market, position_id


class TestAStopThatClosesThePositionVoidsTheCompetingTarget:
    """RISK_ENGINE.md §10: "stop, alvo e fechamento manual concorrentes
    compartilham a quantidade vendável sob o mesmo lock — não podem vender a
    mesma unidade duas vezes".

    ``allocate_sellable`` gives the stop first claim on the position (priority
    0, RISK_ENGINE.md §10's ordering) regardless of which protection actually
    crossed this cycle — proved directly: the stop's own ``intended_qty``
    (10, the whole position) leaves the target's computed share at **zero**
    even though the target is never attempted this cycle at all (its trigger
    never crossed). When the stop's fill empties the position,
    ``_void_the_other_protections`` retires the target in the very same
    transaction — never a fictitious partial fill for a protection that was
    never even tried.

    **O que refuta:** the sum sold exceeding 10; the target ending
    ``fulfilled`` with a fill that never happened instead of ``voided``; the
    target's ``filled_qty`` being anything other than zero.
    """

    async def test_the_position_sells_at_most_ten_and_the_target_is_voided_not_fulfilled(
        self,
        engine: AsyncEngine,
        factory: async_sessionmaker[AsyncSession],
        wallet: Wallet,
    ) -> None:
        market, _position_id = await _position_of_ten(factory, wallet)

        # The tape gaps straight through the stop with a deep book, received
        # after the declared latency and evaluated a moment later — the two
        # instants a real cycle always has (spec §12 trap 2 bars a wall clock,
        # never a print evaluated in the very cycle that printed it).
        fire_at = at(minutes=1)
        book_at = fire_at + timedelta(milliseconds=300)
        cycle_at = fire_at + timedelta(seconds=1)
        fired = await run_protection(
            factory,
            wallet,
            static_data(
                market,
                SpotSnapshot(
                    market=market.identity,
                    book=spot_book(
                        market, received_at=book_at, bid=Decimal(95), ask=Decimal("95.05")
                    ),
                    trades=(spot_trade(market, price=Decimal(95), ts=fire_at, trade_id=1),),
                    avg_price=Decimal(100),
                ),
            ),
            now=cycle_at,
        )
        # Only the stop is ``due()`` this cycle — the target's own trigger
        # (105) never crossed, so it gets no attempt of its own at all.
        assert [(o.trigger, o.status) for o in fired] == [("stop", "filled")]

        sold = await sum_sold(engine, wallet)
        assert sold <= POSITION_QTY
        assert sold == POSITION_QTY  # the whole position left in one attempt

        positions = await read_positions(engine, wallet)
        assert len(positions) == 1
        assert positions[0].qty == Decimal(0)
        assert positions[0].status == "closed"

        intents = await read_exit_intents(engine, wallet)
        by_key = {row.protection_key: row for row in intents}
        assert by_key["stop"].state == ExitIntentState.FULFILLED.value
        assert by_key["stop"].filled_qty == by_key["stop"].intended_qty == POSITION_QTY
        # Never "fulfilled" with a fill that did not happen: the target was
        # never even attempted, so it is voided, not closed as if six units
        # had really been sold.
        assert by_key["target:1"].state == ExitIntentState.VOIDED.value
        assert by_key["target:1"].filled_qty == Decimal(0)
        assert "competing protection" in (by_key["target:1"].closed_reason or "")


class TestARedeliveredExitReportMovesNothingASecondTime:
    """§12 trap 6 applied: no tolerance anywhere — the two reads are compared
    byte-for-byte as ``Decimal``, not "close enough".

    **O que refuta:** a second row in ``fills``/``orders``; a position
    quantity or an intention's ``filled_qty`` that moved a second time.
    """

    async def test_replaying_the_same_attempt_id_writes_nothing_and_moves_no_cash(
        self,
        engine: AsyncEngine,
        factory: async_sessionmaker[AsyncSession],
        wallet: Wallet,
    ) -> None:
        market, _position_id = await _position_of_ten(factory, wallet)
        fire_at = at(minutes=1)
        book_at = fire_at + timedelta(milliseconds=300)
        cycle_at = fire_at + timedelta(seconds=1)
        attempt_id = uuid.UUID("0193f7f0-0000-7000-8000-00000000da74")
        reference = wallet_ref(wallet)

        # Built **once**: the whole point of a replay is the same report
        # arriving twice, not two different snapshots of a position that the
        # first call already closed (``load_open_positions`` would find
        # nothing on a second read — the position is gone by design).
        async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
            loaded_market = await load_market(session, market.id)
            assert loaded_market is not None
            position = (await load_open_positions(session, wallet=reference))[0]
            intent = next(
                i
                for i in await live_intents(session, wallet=reference, market=loaded_market)
                if i.protection_key == "stop"
            )
        attempt = ExitAttempt.for_intent(
            intent,
            qty=position.qty,
            decision_at=fire_at,
            position_qty=position.qty,
            attempt_id=attempt_id,
        )
        report = PaperExecutionAdapter().submit_protection_exit(
            attempt,
            position.qty,
            spot_book(market, received_at=book_at, bid=Decimal(95), ask=Decimal("95.05")),
            spot_trade(market, price=Decimal(95), ts=fire_at, trade_id=1),
            market_reference(market).filters,
            market_reference(market).fees,
            cycle_at,
            avg_price=Decimal(100),
        )

        async def apply_once() -> str:
            async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
                application = await apply_exit(
                    session,
                    wallet=reference,
                    market=loaded_market,
                    attempt=attempt,
                    report=report,
                    position=position,
                    now=cycle_at,
                    source="test_double",
                )
                return "replayed" if application.replayed else application.status

        assert await apply_once() == "filled"
        before_fills = await count_rows(engine, wallet, "fills")
        before_orders = await count_rows(engine, wallet, "orders")
        async with engine.begin() as connection:
            before_row = (
                await connection.execute(
                    text(
                        "SELECT p.qty AS position_qty, i.filled_qty AS intent_filled "
                        "FROM positions p JOIN portfolio_exit_intents i "
                        "ON i.position_id = p.id WHERE p.portfolio_id = :pf "
                        "AND i.protection_key = 'stop'"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()

        assert await apply_once() == "replayed"

        after_fills = await count_rows(engine, wallet, "fills")
        after_orders = await count_rows(engine, wallet, "orders")
        async with engine.begin() as connection:
            after_row = (
                await connection.execute(
                    text(
                        "SELECT p.qty AS position_qty, i.filled_qty AS intent_filled "
                        "FROM positions p JOIN portfolio_exit_intents i "
                        "ON i.position_id = p.id WHERE p.portfolio_id = :pf "
                        "AND i.protection_key = 'stop'"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).one()

        assert (after_fills, after_orders) == (before_fills, before_orders)
        assert (after_row.position_qty, after_row.intent_filled) == (
            before_row.position_qty,
            before_row.intent_filled,
        )


class TestTwoRealSessionsNeverOversellOnePosition:
    """Two distinct connections racing the *same* protection cycle at the same
    instant — the pattern already proved in
    ``services/execution-worker/tests/test_concurrency.py``, reproduced here
    against the §0 SOL market/numbers so this suite does not have to trust a
    number it never measured itself.

    **O que refuta:** both sessions selling 10, for a total of 20; the second
    session's row lock never blocking on the first's.
    """

    async def test_two_concurrent_protection_cycles_sell_the_position_at_most_once(
        self,
        engine: AsyncEngine,
        factory: async_sessionmaker[AsyncSession],
        wallet: Wallet,
    ) -> None:
        market, _position_id = await _position_of_ten(factory, wallet)
        fire_at = at(minutes=1)
        book_at = fire_at + timedelta(milliseconds=300)
        cycle_at = fire_at + timedelta(seconds=1)
        data = static_data(
            market,
            SpotSnapshot(
                market=market.identity,
                book=spot_book(market, received_at=book_at, bid=Decimal(95), ask=Decimal("95.05")),
                trades=(spot_trade(market, price=Decimal(95), ts=fire_at, trade_id=1),),
                avg_price=Decimal(100),
            ),
        )

        async def cycle() -> tuple[str, ...]:
            outcomes = await run_protection(factory, wallet, data, now=cycle_at)
            return tuple(o.status for o in outcomes)

        first, second = await asyncio.gather(cycle(), cycle())

        sold = await sum_sold(engine, wallet)
        positions = await read_positions(engine, wallet)
        assert sold <= POSITION_QTY
        assert sold == POSITION_QTY
        assert positions[0].qty == Decimal(0)
        # Exactly one of the two cycles is the one that actually filled the
        # stop; the other found nothing left to sell (or nothing due).
        assert ("filled",) in (first, second)
