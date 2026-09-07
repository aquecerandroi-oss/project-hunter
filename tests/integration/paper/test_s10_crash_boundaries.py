"""§10 — crash at each boundary: no observable state half-written.

**Objetivo:** the three boundaries the dispatch names explicitly —

1. a fill and the durable protection it arms are written **in the same
   transaction**: killing the process between them is unobservable, because
   there is no commit between them to kill between;
2. redelivering an entry report after a "death" before the acknowledgement
   (the at-least-once guarantee any consumer of this worker's inputs would
   give) applies the effect **exactly once**, never twice and never zero
   times for the *first* delivery;
3. a kill switch transition written without the matching audit row in the
   same transaction is refused **by the database itself**
   (``portfolios_kill_switch_is_audited``, a deferred constraint trigger,
   ``docs/DATABASE.md`` §18.7) — atomic by construction, and this proves the
   construction, not a promise about it.

The "kill" in 1 and 2 is a raised exception inside the transaction that would
have committed the effect — never a mock that "simulates" a crash while
leaving Python objects alive in memory (spec §12 trap 7): the assertion is
that Postgres itself rolled everything back, read from a **fresh** connection
after the fact.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from hunter_core.db.session import tenant_session
from hunter_execution_worker.market_data import SpotSnapshot

from .conftest import (
    NOW,
    admit_entry,
    at,
    count_rows,
    liquidity_for,
    read_positions,
    run_entries,
    spot_book,
    spot_trade,
    static_data,
    wallet_ref,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from .conftest import Wallet

pytestmark = [pytest.mark.integration]

ENTRY_PRICE = Decimal(100)
WORKER_ROLE = "hunter_worker"


class TestAFillAndItsProtectionAreOneTransactionNeverTwoCommits:
    """Boundary 3/4 of §10's table, combined at the point this worker actually
    exposes it: ``apply_entry`` writes ``orders``, opens the ``position`` and
    inserts the durable ``portfolio_exit_intents`` row in **one** function,
    under **one** session, with **one** commit at the ``tenant_session``
    context's exit. Raising between the fill and the intention proves there is
    no earlier commit to have survived the "kill".

    **O que refuta:** any row surviving in ``orders``, ``fills`` or
    ``positions`` after the transaction that would have written the intention
    raised and rolled back.
    """

    async def test_a_raise_before_the_intent_rolls_back_the_order_fill_and_position_too(
        self, engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
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
        data = static_data(
            market,
            SpotSnapshot(
                market=market.identity,
                book=spot_book(market, received_at=book_at, bid=ENTRY_PRICE, ask=ENTRY_PRICE),
                trades=(spot_trade(market, price=ENTRY_PRICE, ts=fill_at, trade_id=1),),
                avg_price=ENTRY_PRICE,
            ),
        )
        now = fill_at + timedelta(seconds=1)

        class _KilledAfterTheFill(RuntimeError):
            """Stands in for a process death: nothing catches this before the
            transaction's own rollback does."""

        with (
            patch(
                "hunter_execution_worker.apply.insert_intent",
                side_effect=_KilledAfterTheFill(
                    "killed after order+fill+position, before the intent"
                ),
            ),
            pytest.raises(_KilledAfterTheFill),
        ):
            await run_entries(factory, wallet, data, now=now)

        # A fresh connection, never the one the killed transaction used —
        # this is what makes the check honest about what Postgres actually
        # kept, not what a still-alive Python object claims happened.
        assert await count_rows(engine, wallet, "orders") == 0
        assert await count_rows(engine, wallet, "fills") == 0
        assert await count_rows(engine, wallet, "positions") == 0
        assert await count_rows(engine, wallet, "portfolio_exit_intents") == 0


class TestARedeliveredEntryAfterADeathBeforeTheAckAppliesOnceNotTwice:
    """Boundary 2 of the dispatch: the entry's own idempotency
    (``uq_orders_client_order_id`` on ``entry:{proposal_id}``), exercised the
    way V4 already exercised the **exit** side — this is the **entry** side,
    which is a different function (``apply_entry``, not ``apply_exit``) and
    was not covered there.

    **O que refuta:** a second ``positions`` row for one proposal; the cash
    moving twice; the second call reporting anything but ``replayed=True``.
    """

    async def test_the_same_entry_report_applied_twice_opens_one_position_only(
        self, engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        from hunter_core.execution.entries import MarketEntryOrder
        from hunter_core.execution.paper import PaperExecutionAdapter
        from hunter_execution_worker.apply import apply_entry
        from hunter_execution_worker.reference import load_market
        from hunter_risk.decision import RiskDecision

        market = wallet.market("SOLUSDT")
        decision_result = await admit_entry(
            factory,
            wallet,
            market,
            now=NOW,
            marks={market.id: ENTRY_PRICE},
            liquidity=liquidity_for(market, as_of=NOW, last_price=ENTRY_PRICE),
        )
        assert decision_result.approved
        fill_at = at(seconds=1)
        book_at = fill_at + timedelta(milliseconds=300)
        reference = wallet_ref(wallet)

        async def apply_once() -> str:
            async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
                row = (
                    await session.execute(
                        text("SELECT risk_decision FROM trade_proposals WHERE id = :id"),
                        {"id": decision_result.proposal_id},
                    )
                ).one()
                decision = RiskDecision.model_validate(row.risk_decision)
                order = MarketEntryOrder.from_decision(decision, decision_at=NOW)
                loaded_market = await load_market(session, market.id)
                assert loaded_market is not None
                report = PaperExecutionAdapter().submit_market_entry(
                    order,
                    spot_book(market, received_at=book_at, bid=ENTRY_PRICE, ask=ENTRY_PRICE),
                    spot_trade(market, price=ENTRY_PRICE, ts=fill_at, trade_id=1),
                    loaded_market.filters,
                    loaded_market.fees,
                    fill_at + timedelta(seconds=1),
                    avg_price=ENTRY_PRICE,
                )
                application = await apply_entry(
                    session,
                    wallet=reference,
                    market=loaded_market,
                    order=order,
                    report=report,
                    now=fill_at + timedelta(seconds=1),
                    source="test_double",
                )
                return "replayed" if application.replayed else application.status

        assert await apply_once() == "filled"
        assert await count_rows(engine, wallet, "positions") == 1
        assert await count_rows(engine, wallet, "orders") == 1
        assert await count_rows(engine, wallet, "fills") == 1
        before_qty = (await read_positions(engine, wallet))[0].qty

        # The "redelivery after a death before the ack": the exact same
        # report, as if the message had never been acknowledged and came
        # back around.
        assert await apply_once() == "replayed"
        assert await count_rows(engine, wallet, "positions") == 1
        assert await count_rows(engine, wallet, "orders") == 1
        assert await count_rows(engine, wallet, "fills") == 1
        after_qty = (await read_positions(engine, wallet))[0].qty
        assert after_qty == before_qty


class TestAKillSwitchTransitionWithoutAnAuditRowIsRefusedByThePostgresConstraint:
    """Boundary 6 of §10's table: ``portfolios_kill_switch_is_audited`` is a
    ``DEFERRABLE INITIALLY DEFERRED`` constraint trigger — it fires at
    **commit**, not at the ``UPDATE`` statement itself, which is exactly why
    this has to be a real transaction commit and not a statement-level check.

    **O que refuta:** a commit that succeeds after moving
    ``portfolios.kill_switch_state`` without a same-transaction,
    same-``xid`` ``kill_switch_transitions`` row naming the same
    ``from_state``/``to_state``.
    """

    async def test_moving_the_latch_without_the_matching_transition_row_fails_at_commit(
        self, engine: AsyncEngine, wallet: Wallet
    ) -> None:
        async with engine.connect() as connection:
            trans = await connection.begin()
            await connection.execute(
                text(
                    "UPDATE portfolios SET kill_switch_state = 'WARNING' "
                    "WHERE id = :id AND organization_id = :org"
                ),
                {"id": wallet.portfolio_id, "org": wallet.org_id},
            )
            with pytest.raises(DBAPIError, match="without an audited transition"):
                await trans.commit()
            await trans.rollback()

        async with engine.begin() as connection:
            latch = await connection.scalar(
                text("SELECT kill_switch_state FROM portfolios WHERE id = :id"),
                {"id": wallet.portfolio_id},
            )
        assert latch == "ACTIVE"  # the refused move never took effect

    async def test_the_same_move_with_its_audit_row_in_the_same_transaction_commits(
        self, engine: AsyncEngine, wallet: Wallet
    ) -> None:
        """The differential half of the proof above: the guard is narrow — it
        refuses an *unaudited* move, never a move at all. Without this, the
        first test could pass for the wrong reason (any ``UPDATE`` of that
        column failing, audited or not)."""
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO kill_switch_transitions (id, organization_id, scope, scope_id, "
                    "from_state, to_state, reason, actor_type, actor_id, evidence, created_at) "
                    "VALUES (gen_random_uuid(), :org, 'portfolio', :pf, 'ACTIVE', 'WARNING', "
                    "'s10 proof', 'system', NULL, "
                    '\'{"daily_loss_pct": "0.0110"}\'::jsonb, now())'
                ),
                {"org": wallet.org_id, "pf": wallet.portfolio_id},
            )
            await connection.execute(
                text(
                    "UPDATE portfolios SET kill_switch_state = 'WARNING' "
                    "WHERE id = :id AND organization_id = :org"
                ),
                {"id": wallet.portfolio_id, "org": wallet.org_id},
            )
        # No exception on __aexit__'s commit: the audited move is accepted.
        async with engine.begin() as connection:
            latch = await connection.scalar(
                text("SELECT kill_switch_state FROM portfolios WHERE id = :id"),
                {"id": wallet.portfolio_id},
            )
        assert latch == "WARNING"
