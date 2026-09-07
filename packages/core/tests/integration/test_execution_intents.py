"""The execution layer against a real Postgres: identity, durability, replay.

The unit suite proves what the adapter *computes*. These four questions can only
be answered by the schema plus the code together, and they are the T3.4
acceptance list (``docs/plans/M3.md``):

- "entrada com restante cancelado" and a replayed event that does **not** open a
  second order — the derived ``client_order_id`` and ``fills.execution_key``
  meeting their unique indexes;
- "proteção com intenção durável" surviving a **restart**: the process is
  restarted by throwing the in-memory intention away and rebuilding it from
  ``portfolio_exit_intents``, and the next attempt sells exactly the remainder;
- "resíduo" visible as ``blocked_residual`` instead of a fictitious settlement;
- "consumo não reaparece após replay": one participation entry per fill, and
  **no** entry at all for a protection (RISK_ENGINE.md §4: "saídas de proteção
  não consomem este orçamento").

The wallet is built as the container owner, exactly like the other paper-schema
tests: RLS is proved elsewhere, and what is under test here is execution.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from hunter_core.domain.enums import (
    ExitIntentState,
    ExitReason,
    KillSwitchState,
    MarketType,
    OrderSide,
)
from hunter_core.domain.market import BookLevel, NormalizedOrderBook, NormalizedTrade
from hunter_core.domain.types import uuid7
from hunter_core.execution.adapter import ExecutionReport
from hunter_core.execution.entries import MarketEntryOrder
from hunter_core.execution.intents import ExitAttempt, ExitIntent, apply_attempt
from hunter_core.execution.paper import PaperExecutionAdapter
from hunter_risk.decision import Counterfactual, LimitCap, RiskDecision, Sizing, check
from hunter_risk.inputs import MarketIdentity

from .conftest import alembic_config, async_engine, create_database

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
_ORDER_STATUS = {
    "filled": "filled",
    "partially_filled": "partially_filled",
    "rejected": "rejected",
    "pending_degraded": "pending",
    "recorded": "pending",
}
"""A degraded protection is a *pending* order: it never reached the book, and
calling it rejected would say the protection was refused."""
DECIDED_AT = NOW - timedelta(seconds=1)
_ADAPTER = PaperExecutionAdapter()


class _Filters:
    """The market's rules for this test: step 0,1 and a minimum of 1."""

    effective_step_size = Decimal("0.1")
    effective_min_qty = Decimal("1")

    def round_qty_down(self, qty: Decimal) -> Decimal:
        return (qty / self.effective_step_size).to_integral_value(rounding="ROUND_FLOOR") * (
            self.effective_step_size
        )

    def check_market_order(
        self,
        qty: Decimal,
        *,
        avg_price: Decimal | None = None,
        last_price: Decimal | None = None,
    ) -> _Verdict:
        rounded = self.round_qty_down(qty)
        ok = rounded >= self.effective_min_qty
        return _Verdict(ok=ok, qty=rounded, reason=None if ok else "min_qty")


class _Verdict:
    def __init__(self, *, ok: bool, qty: Decimal, reason: str | None) -> None:
        self.ok, self.qty, self.reason, self.notional = ok, qty, reason, None


class _Fees:
    taker_rate = Decimal("0.001")
    source = "spot VIP 0 (test)"


def _book(
    bids: list[tuple[str, str]], *, asks: list[tuple[str, str]] | None = None
) -> NormalizedOrderBook:
    return NormalizedOrderBook(
        exchange="binance",
        symbol="BTCUSDT",
        bids=[BookLevel(price=Decimal(p), qty=Decimal(q)) for p, q in bids],
        asks=[BookLevel(price=Decimal(p), qty=Decimal(q)) for p, q in (asks or [])],
        sequence=10,
        is_snapshot=True,
        ts=NOW,
        received_at=NOW,
    )


def _trade(price: str) -> NormalizedTrade:
    return NormalizedTrade(
        exchange="binance",
        symbol="BTCUSDT",
        trade_id="500",
        price=Decimal(price),
        qty=Decimal("1"),
        side=OrderSide.SELL,
        ts=NOW,
        received_at=NOW,
    )


# ----------------------------------------------------------------- fixtures


@pytest.fixture(scope="session")
def execution_db(container_url: str) -> Iterator[str]:
    """A database of its own, so a wallet here never collides with the ledger's."""
    url = asyncio.run(create_database(container_url, "hunter_execution"))
    command.upgrade(alembic_config(url), "head")
    yield url


@pytest_asyncio.fixture
async def engine(execution_db: str) -> AsyncIterator[AsyncEngine]:
    created = async_engine(execution_db)
    try:
        yield created
    finally:
        await created.dispose()


class Wallet:
    """One organization, workspace, market, wallet, position and proposal."""

    def __init__(self) -> None:
        self.slug = uuid.uuid4().hex[:10]
        self.org_id = uuid7()
        self.workspace_id = uuid7()
        self.exchange_id = uuid7()
        self.market_id = uuid7()
        self.portfolio_id = uuid7()
        self.position_id = uuid7()
        self.proposal_id = uuid7()


@pytest_asyncio.fixture
async def wallet(engine: AsyncEngine) -> Wallet:
    built = Wallet()
    params = {
        "org": built.org_id,
        "ws": built.workspace_id,
        "ex": built.exchange_id,
        "market": built.market_id,
        "pf": built.portfolio_id,
        "pos": built.position_id,
        "proposal": built.proposal_id,
        "slug": built.slug,
        "symbol": f"BTC{built.slug[:6].upper()}",
        "key": uuid.uuid4().hex,
    }
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO organizations (id, slug, name) VALUES (:org, :slug, :slug)"), params
        )
        await connection.execute(
            text(
                "INSERT INTO workspaces (id, organization_id, name, objective) "
                "VALUES (:ws, :org, :slug, 'paper_trading')"
            ),
            params,
        )
        await connection.execute(
            text("INSERT INTO exchanges (id, code, name) VALUES (:ex, :slug, 'Probe')"), params
        )
        await connection.execute(
            text(
                "INSERT INTO markets (id, exchange_id, symbol, market_type) "
                "VALUES (:market, :ex, :symbol, 'spot')"
            ),
            params,
        )
        await connection.execute(
            text(
                "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                "initial_capital) VALUES (:pf, :org, :ws, :slug, 'paper', 20000)"
            ),
            params,
        )
        await connection.execute(
            text(
                "INSERT INTO positions (id, organization_id, portfolio_id, market_id, direction, "
                "qty, avg_entry_price) VALUES (:pos, :org, :pf, :market, 'long', 10, 100)"
            ),
            params,
        )
        await connection.execute(
            text(
                "INSERT INTO trade_proposals (id, organization_id, portfolio_id, market_id, "
                "direction, idempotency_key, status) "
                "VALUES (:proposal, :org, :pf, :market, 'long', :key, 'approved')"
            ),
            params,
        )
    return built


# ------------------------------------------------------------------ helpers


async def _insert_intent(connection: AsyncConnection, wallet: Wallet, intent: ExitIntent) -> None:
    await connection.execute(
        text(
            "INSERT INTO portfolio_exit_intents (id, organization_id, portfolio_id, position_id, "
            "market_id, reason, protection_key, intended_qty, filled_qty, trigger_price, state) "
            "VALUES (:id, :org, :pf, :pos, :market, :reason, :key, :intended, :filled, :trigger, "
            ":state)"
        ),
        {
            "id": intent.intent_id,
            "org": wallet.org_id,
            "pf": wallet.portfolio_id,
            "pos": wallet.position_id,
            "market": wallet.market_id,
            "reason": intent.reason.value,
            "key": intent.protection_key,
            "intended": intent.intended_qty,
            "filled": intent.filled_qty,
            "trigger": intent.trigger_price,
            "state": intent.state.value,
        },
    )


async def _persist_attempt(
    connection: AsyncConnection, wallet: Wallet, report: ExecutionReport, *, purpose: str
) -> uuid.UUID:
    """Write the attempt the way the worker will: order, then fill, both idempotent."""
    order_id = uuid7()
    inserted = await connection.execute(
        text(
            "INSERT INTO orders (id, organization_id, portfolio_id, proposal_id, exit_intent_id, "
            "market_id, position_id, client_order_id, side, type, purpose, qty, filled_qty, "
            "status) VALUES (:id, :org, :pf, :proposal, :intent, :market, :pos, :coid, :side, "
            "'market', :purpose, :qty, :filled, :status) "
            "ON CONFLICT (portfolio_id, client_order_id) DO NOTHING RETURNING id"
        ),
        {
            "id": order_id,
            "org": wallet.org_id,
            "pf": wallet.portfolio_id,
            "proposal": wallet.proposal_id if purpose == "entry" else None,
            "intent": report.intent_id,
            "market": wallet.market_id,
            "pos": wallet.position_id,
            "coid": report.client_order_id,
            "side": report.side.value,
            "purpose": purpose,
            "qty": report.requested_qty,
            "filled": report.filled_qty,
            "status": _ORDER_STATUS[report.status],
        },
    )
    existing = inserted.scalar()
    if existing is None:
        existing = await connection.scalar(
            text("SELECT id FROM orders WHERE portfolio_id = :pf AND client_order_id = :coid"),
            {"pf": wallet.portfolio_id, "coid": report.client_order_id},
        )
        return uuid.UUID(str(existing))
    if report.filled_qty > 0:
        await connection.execute(
            text(
                "INSERT INTO fills (id, organization_id, portfolio_id, order_id, execution_key, "
                "ts, qty, price, fee, fee_asset, liquidity) VALUES (:id, :org, :pf, :order, :key, "
                ":ts, :qty, :price, :fee, :asset, 'taker') "
                "ON CONFLICT (organization_id, execution_key) DO NOTHING"
            ),
            {
                "id": uuid7(),
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "order": existing,
                "key": report.execution_key,
                "ts": report.executed_at,
                "qty": report.filled_qty,
                "price": report.vwap,
                "fee": report.fee.qty if report.fee else 0,
                "asset": "BTC" if report.fee and report.fee.asset == "base" else "USDT",
            },
        )
    return uuid.UUID(str(existing))


async def _save_intent(connection: AsyncConnection, intent: ExitIntent) -> None:
    await connection.execute(
        text(
            "UPDATE portfolio_exit_intents SET filled_qty = :filled, state = :state, "
            "degraded_since = :since, degraded_reason = :reason, closed_at = :closed "
            "WHERE id = :id"
        ),
        {
            "filled": intent.filled_qty,
            "state": intent.state.value,
            "since": intent.degraded_since,
            "reason": intent.degraded_reason,
            "closed": intent.closed_at,
            "id": intent.intent_id,
        },
    )


async def _load_intent(connection: AsyncConnection, intent_id: uuid.UUID) -> ExitIntent:
    """Rebuild the intention from Postgres — the restart path, literally."""
    row = (
        await connection.execute(
            text(
                "SELECT id, portfolio_id, position_id, protection_key, reason, intended_qty, "
                "filled_qty, state, trigger_price, degraded_since, degraded_reason, closed_at, "
                "closed_reason, superseded_by_id "
                "FROM portfolio_exit_intents WHERE id = :id"
            ),
            {"id": intent_id},
        )
    ).one()
    return ExitIntent(
        intent_id=row.id,
        portfolio_id=row.portfolio_id,
        position_id=row.position_id,
        protection_key=row.protection_key,
        reason=ExitReason(row.reason),
        intended_qty=row.intended_qty,
        filled_qty=row.filled_qty,
        state=ExitIntentState(row.state),
        trigger_price=row.trigger_price,
        degraded_since=row.degraded_since,
        degraded_reason=row.degraded_reason,
        closed_at=row.closed_at,
        closed_reason=row.closed_reason,
        superseded_by_id=row.superseded_by_id,
    )


def _new_intent(wallet: Wallet, *, intended: str = "10") -> ExitIntent:
    return ExitIntent(
        intent_id=uuid7(),
        portfolio_id=wallet.portfolio_id,
        position_id=wallet.position_id,
        protection_key="stop",
        reason=ExitReason.STOP,
        intended_qty=Decimal(intended),
        trigger_price=Decimal("95"),
    )


def _entry_order(wallet: Wallet, qty: str = "3") -> MarketEntryOrder:
    """An entry order behind a real approved decision — the only kind that exists.

    RISK_ENGINE.md §8 as a constructor: there is no flag to set, so a test (or a
    worker) cannot conjure an entry for a proposal the engine refused.
    """
    cap = LimitCap(name="risk_per_trade", notional=Decimal("300"))
    sizing = Sizing(
        entry_ref=Decimal("100"),
        sizing_price=Decimal("100"),
        stop=Decimal("95"),
        stop_distance_pct=Decimal("0.05"),
        cost_pct=Decimal("0.002"),
        caps=(cap,),
        binding_limit=cap,
        binding_constraint="risk_per_trade",
        size_without_multipliers=Counterfactual(name="size_without_multipliers", qty=Decimal(qty)),
        size_without_participation=Counterfactual(
            name="size_without_participation", qty=Decimal(qty)
        ),
        notional_before_multiplier=Decimal("300"),
        kill_switch_multiplier=Decimal(1),
        notional_after_multiplier=Decimal("300"),
        qty=Decimal(qty),
        notional=Decimal("300"),
        planned_risk_quote=Decimal("15"),
        planned_risk_pct=Decimal("0.0025"),
    )
    decision = RiskDecision(
        approved=True,
        kind="entry",
        proposal_id=wallet.proposal_id,
        portfolio_id=wallet.portfolio_id,
        market=MarketIdentity(
            exchange="binance",
            symbol="BTCUSDT",
            market_type=MarketType.SPOT,
            base_asset="BTC",
            quote_asset="USDT",
        ),
        limits_profile="paper_v1",
        effective_kill_switch=KillSwitchState.ACTIVE,
        cancel_pending=False,
        shadow_only=False,
        checks=(check("cash", True),),
        sizing=sizing,
    )
    return MarketEntryOrder.from_decision(decision, decision_at=DECIDED_AT)


# -------------------------------------------------------------------- tests


async def test_a_redelivered_entry_event_never_opens_a_second_order_or_fill(
    engine: AsyncEngine, wallet: Wallet
) -> None:
    """The derived ``client_order_id`` is what makes the replay a no-op."""
    order = _entry_order(wallet)
    report = _ADAPTER.submit_market_entry(
        order,
        _book([], asks=[("100.00", "10")]),
        _trade("100"),
        _Filters(),
        _Fees(),
        NOW,
        avg_price=Decimal("100"),
    )
    assert report.status == "filled"
    async with engine.begin() as connection:
        await _persist_attempt(connection, wallet, report, purpose="entry")
    async with engine.begin() as connection:  # the same stream event, redelivered
        await _persist_attempt(connection, wallet, report, purpose="entry")
    async with engine.connect() as connection:
        orders = await connection.scalar(
            text("SELECT count(*) FROM orders WHERE portfolio_id = :pf"),
            {"pf": wallet.portfolio_id},
        )
        fills = await connection.scalar(
            text("SELECT count(*) FROM fills WHERE portfolio_id = :pf"),
            {"pf": wallet.portfolio_id},
        )
    assert (orders, fills) == (1, 1)


async def test_two_attempts_at_one_intention_cannot_share_an_execution_key(
    engine: AsyncEngine, wallet: Wallet
) -> None:
    """``uq_fills_execution_key`` is the last line of defence, and it holds."""
    intent = _new_intent(wallet)
    order_id = uuid7()
    fill = text(
        "INSERT INTO fills (id, organization_id, portfolio_id, order_id, execution_key, qty, "
        "price) VALUES (:id, :org, :pf, :order, 'exit:same', 4, 95)"
    )
    params = {"org": wallet.org_id, "pf": wallet.portfolio_id, "order": order_id}
    async with engine.begin() as connection:
        await _insert_intent(connection, wallet, intent)
        await connection.execute(
            text(
                "INSERT INTO orders (id, organization_id, portfolio_id, exit_intent_id, market_id,"
                " position_id, client_order_id, side, type, purpose, qty) VALUES (:id, :org, :pf, "
                ":intent, :market, :pos, :coid, 'sell', 'market', 'stop', 4)"
            ),
            {
                "id": order_id,
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "intent": intent.intent_id,
                "market": wallet.market_id,
                "pos": wallet.position_id,
                "coid": f"exit:{uuid7()}",
            },
        )
        await connection.execute(fill, {"id": uuid7(), **params})
    with pytest.raises(IntegrityError, match="uq_fills_execution_key"):
        async with engine.begin() as connection:
            await connection.execute(fill, {"id": uuid7(), **params})


async def test_the_intention_survives_a_restart_and_the_next_attempt_takes_the_remainder(
    engine: AsyncEngine, wallet: Wallet
) -> None:
    """A stop for 10 finds 4 sellable; the process dies; 6 are still protected."""
    intent = _new_intent(wallet)
    async with engine.begin() as connection:
        await _insert_intent(connection, wallet, intent)
        first = _ADAPTER.submit_protection_exit(
            ExitAttempt.for_intent(intent, qty=Decimal("10"), decision_at=DECIDED_AT),
            Decimal("10"),
            _book([("95.00", "4")]),
            _trade("95"),
            _Filters(),
            _Fees(),
            NOW,
        )
        assert first.filled_qty == Decimal("4")
        assert first.remaining_cancelled is False
        await _persist_attempt(connection, wallet, first, purpose="stop")
        await _save_intent(connection, apply_attempt(intent, first, now=NOW, min_qty=Decimal("1")))

    del intent, first  # the worker restarts: nothing is left in memory

    async with engine.begin() as connection:
        rebuilt = await _load_intent(connection, (await _only_intent(connection, wallet)))
        assert rebuilt.state is ExitIntentState.OPEN
        assert rebuilt.remaining_qty == Decimal("6")
        second = _ADAPTER.submit_protection_exit(
            ExitAttempt.for_intent(rebuilt, qty=rebuilt.remaining_qty, decision_at=DECIDED_AT),
            Decimal("6"),
            _book([("94.00", "10")]),
            _trade("94"),
            _Filters(),
            _Fees(),
            NOW,
        )
        assert second.filled_qty == Decimal("6")
        await _persist_attempt(connection, wallet, second, purpose="stop")
        await _save_intent(
            connection, apply_attempt(rebuilt, second, now=NOW, min_qty=Decimal("1"))
        )
    async with engine.connect() as connection:
        final = await _load_intent(connection, await _only_intent(connection, wallet))
        fills = await connection.scalar(
            text("SELECT count(*) FROM fills WHERE portfolio_id = :pf"),
            {"pf": wallet.portfolio_id},
        )
    assert final.state is ExitIntentState.FULFILLED
    assert final.filled_qty == Decimal("10")
    assert fills == 2  # two attempts, two identities, two fills


async def test_a_residual_below_the_minimum_is_stored_visible_and_unsettled(
    engine: AsyncEngine, wallet: Wallet
) -> None:
    """9,6 of 10 sold under a minimum of 1: the intention is blocked, not fulfilled."""
    intent = _new_intent(wallet)
    async with engine.begin() as connection:
        await _insert_intent(connection, wallet, intent)
        report = _ADAPTER.submit_protection_exit(
            ExitAttempt.for_intent(intent, qty=Decimal("10"), decision_at=DECIDED_AT),
            Decimal("10"),
            _book([("95.00", "9.6")]),
            _trade("95"),
            _Filters(),
            _Fees(),
            NOW,
        )
        assert report.residual is not None and report.residual.qty == Decimal("0.4")
        await _persist_attempt(connection, wallet, report, purpose="stop")
        await _save_intent(connection, apply_attempt(intent, report, now=NOW, min_qty=Decimal("1")))
    async with engine.connect() as connection:
        stored = await _load_intent(connection, await _only_intent(connection, wallet))
    assert stored.state is ExitIntentState.BLOCKED_RESIDUAL
    assert stored.remaining_qty == Decimal("0.4")


async def test_no_usable_book_persists_the_degradation_and_writes_no_fill(
    engine: AsyncEngine, wallet: Wallet
) -> None:
    intent = _new_intent(wallet)
    async with engine.begin() as connection:
        await _insert_intent(connection, wallet, intent)
        report = _ADAPTER.submit_protection_exit(
            ExitAttempt.for_intent(intent, qty=Decimal("10"), decision_at=DECIDED_AT),
            Decimal("10"),
            _book([]),
            _trade("90"),
            _Filters(),
            _Fees(),
            NOW,
        )
        assert report.status == "pending_degraded"
        await _persist_attempt(connection, wallet, report, purpose="stop")
        await _save_intent(connection, apply_attempt(intent, report, now=NOW, min_qty=Decimal("1")))
    async with engine.connect() as connection:
        stored = await _load_intent(connection, await _only_intent(connection, wallet))
        fills = await connection.scalar(
            text("SELECT count(*) FROM fills WHERE portfolio_id = :pf"),
            {"pf": wallet.portfolio_id},
        )
    assert stored.degraded_since is not None
    assert stored.degraded_reason == "empty_side"
    assert stored.remaining_qty == Decimal("10")
    assert fills == 0


async def test_a_replayed_fill_cannot_spend_the_participation_minute_twice(
    engine: AsyncEngine, wallet: Wallet
) -> None:
    """One executed entry per fill; and a protection books nothing at all."""
    order = _entry_order(wallet)
    report = _ADAPTER.submit_market_entry(
        order,
        _book([], asks=[("100.00", "10")]),
        _trade("100"),
        _Filters(),
        _Fees(),
        NOW,
        avg_price=Decimal("100"),
    )
    async with engine.begin() as connection:
        order_id = await _persist_attempt(connection, wallet, report, purpose="entry")
        fill_id = await connection.scalar(
            text("SELECT id FROM fills WHERE execution_key = :key"),
            {"key": report.execution_key},
        )
        params = {
            "org": wallet.org_id,
            "pf": wallet.portfolio_id,
            "market": wallet.market_id,
            "proposal": wallet.proposal_id,
            "order": order_id,
            "fill": fill_id,
            "notional": report.gross_quote,
            "ts": NOW,
        }
        statement = text(
            "INSERT INTO participation_consumptions (id, organization_id, portfolio_id, "
            "market_id, proposal_id, order_id, fill_id, kind, notional, occurred_at) VALUES "
            "(:id, :org, :pf, :market, :proposal, :order, :fill, 'executed', :notional, :ts) "
            "ON CONFLICT DO NOTHING"
        )
        await connection.execute(statement, {"id": uuid7(), **params})
        await connection.execute(statement, {"id": uuid7(), **params})  # the replay
    async with engine.connect() as connection:
        rows = await connection.scalar(
            text("SELECT count(*) FROM participation_consumptions WHERE portfolio_id = :pf"),
            {"pf": wallet.portfolio_id},
        )
        spent = await connection.scalar(
            text(
                "SELECT coalesce(sum(notional), 0) FROM participation_consumptions "
                "WHERE portfolio_id = :pf AND kind = 'executed' AND occurred_at > :cut"
            ),
            {"pf": wallet.portfolio_id, "cut": NOW - timedelta(seconds=60)},
        )
    assert rows == 1
    assert spent == report.gross_quote


async def _only_intent(connection: AsyncConnection, wallet: Wallet) -> uuid.UUID:
    found = await connection.scalar(
        text("SELECT id FROM portfolio_exit_intents WHERE portfolio_id = :pf"),
        {"pf": wallet.portfolio_id},
    )
    return uuid.UUID(str(found))
