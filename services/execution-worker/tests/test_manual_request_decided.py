"""T3.5c — the manual request the API files is decided by the worker.

``0009_paper_geometry`` gave ``trade_proposals.request_payload`` to the row
the API files (DATABASE.md §21.1); this is the other half, end to end: the
operator's request is filed exactly as ``apps/api/hunter_api/services/admission``
files it — no shortcuts, that module runs unmodified — the worker's admission
cycle reads the pending row back in a **later** transaction (as it would on the
next 1 s pass), rebuilds the ``ProposalRequest`` from nothing but the row and
``markets``, and decides it through the very same
``hunter_core.admission.service.admit`` a bridge candidate goes through. A held
reservation then becomes an order and a fill on the labelled venue
``proof/venue.py`` seeds — the same numbers the 30-minute T3.5 proof used.

Before this, a row filed by the API could only be named
(``pending_request_without_geometry``) and never decided (notes-T3.5.md §5.1).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from proof import venue as proof_venue
from sqlalchemy import text

from hunter_api.auth.principal import Principal
from hunter_api.auth.rbac import OrgContext
from hunter_api.services import admission as adapter
from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import (
    MarketType,
    OrderSide,
    OrganizationRole,
    ProposalStatus,
    TradeDirection,
)
from hunter_core.domain.market import BookLevel, NormalizedOrderBook, NormalizedTrade
from hunter_core.execution.paper import PaperExecutionAdapter
from hunter_core.strategies.envelope import AssumedCosts
from hunter_execution_worker.admission_cycle import (
    decide_requests,
    pending_requests,
    readable_and_unreadable,
    rebuild_request,
)
from hunter_execution_worker.entry import execute_approved_entries
from hunter_execution_worker.manual_inputs import manual_request_inputs
from hunter_execution_worker.market_data import SpotSnapshot, StaticSpotMarketData
from hunter_execution_worker.reference import load_market
from hunter_execution_worker.wallet import WalletRef

from .shadow_builders import ensure_candle_partitions, seed_minute_volumes, set_beta

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WORKER_ROLE = "hunter_worker"
NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
FILL_AT = NOW + timedelta(seconds=1)
COSTS = AssumedCosts(
    spread_bps=Decimal(2), slippage_bps=Decimal(5), fee_bps=Decimal(4), max_entry_delay_s=60
)


def _context(org_id: uuid.UUID) -> OrgContext:
    principal = Principal(
        user_id=uuid.uuid4(), external_auth_id="operator-test", email="operator@example.com"
    )
    return OrgContext(org_id=org_id, role=OrganizationRole.OWNER, principal=principal)


def _snapshot(at: datetime) -> SpotSnapshot:
    """One book and one print, both timestamped ``at``.

    Two different instants are needed, never one: the risk engine's own
    ``data_quality``/``book_depth`` checks refuse a book or a price whose age
    at ``as_of`` is **negative** (``hunter_risk.checks``: ``0 <= age``), so the
    picture admission decides against has to be no younger than the decision
    itself — while ``entry.py``'s ``book_before_latency`` guard requires the
    opposite at fill time: the book has to be **newer** than
    ``decided_at + latency``. Production reconciles the two because the hot
    state keeps moving between the two cycles; a static double has to be told
    twice.
    """
    identity = proof_venue.identity()
    book = NormalizedOrderBook(
        exchange=proof_venue.EXCHANGE,
        symbol=proof_venue.SYMBOL,
        market_type=MarketType.SPOT,
        ts=at,
        received_at=at,
        bids=[BookLevel(price=proof_venue.ENTRY, qty=Decimal(1_000))],
        asks=[BookLevel(price=proof_venue.ENTRY, qty=Decimal(1_000))],
        sequence=None,
        is_snapshot=True,
    )
    trade = NormalizedTrade(
        exchange=proof_venue.EXCHANGE,
        symbol=proof_venue.SYMBOL,
        market_type=MarketType.SPOT,
        ts=at,
        received_at=at,
        trade_id="1",
        price=proof_venue.ENTRY,
        qty=Decimal(1),
        side=OrderSide.BUY,
    )
    return SpotSnapshot(market=identity, book=book, trades=(trade,), avg_price=None)


async def test_a_manual_request_is_filed_decided_and_filled(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    ids = await proof_venue.seed(db_engine, "t35c-manual")
    portfolio_id = await proof_venue.open_wallet(db_session_factory, ids)
    wallet = WalletRef(ids["org"], portfolio_id)

    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE markets SET volume_24h_usd = :v, is_monitored = true WHERE id = :id"),
            {"v": Decimal(120_000_000), "id": ids["market"]},
        )
    await ensure_candle_partitions(db_engine, NOW)
    await seed_minute_volumes(db_engine, ids["market"], now=NOW)
    await set_beta(db_engine, ids["market"], as_of=NOW)

    # --- the API files the request: apps/api/hunter_api/services/admission,
    # untouched, exactly as the operator's route would call it. ---
    async with tenant_session(db_session_factory, ids["org"], db_role="hunter_app") as session:
        filed = await adapter.file_manual_order(
            session,
            context=_context(ids["org"]),
            idempotency_key="t35c-manual-1",
            portfolio_id=portfolio_id,
            market_id=ids["market"],
            market=proof_venue.identity(),
            direction=TradeDirection.LONG,
            entry_ref=proof_venue.ENTRY,
            stop=proof_venue.STOP,
            assumed_costs=COSTS,
            now=NOW,
        )
    assert filed.status == ProposalStatus.PENDING
    assert not filed.decided

    # --- the worker's admission cycle, in a later transaction of its own: it
    # reads the row back, rebuilds the request from row + payload + markets,
    # and decides it against the book as it stood **at** the decision. ---
    admission_data = StaticSpotMarketData(
        {(proof_venue.EXCHANGE, proof_venue.SYMBOL): _snapshot(NOW)}
    )
    async with tenant_session(db_session_factory, ids["org"], db_role=WORKER_ROLE) as session:
        rows = await pending_requests(session, wallet=wallet)
        readable, unreadable = readable_and_unreadable(rows)
        assert unreadable == ()
        assert [row.proposal_id for row in readable] == [filed.proposal_id]

        market = await load_market(session, ids["market"])
        assert market is not None
        inputs = await manual_request_inputs(
            session,
            wallet=wallet,
            market=market,
            data=admission_data,
            policy=PaperExecutionAdapter().policy.marking_policy,
            now=NOW,
            exit_cost_rate=Decimal(0),
        )
        assert not isinstance(inputs, str), inputs
        request = rebuild_request(readable[0], wallet=wallet, market=market)
        assert request.client_key == "t35c-manual-1"
        assert request.entry_ref == proof_venue.ENTRY
        assert request.stop == proof_venue.STOP
        assert request.target is None

        decided = await decide_requests(
            session, wallet=wallet, requests=[(request, inputs)], now=NOW
        )
    assert len(decided) == 1
    result = decided[0]
    assert result.approved, result.decision.rejection_reasons
    assert result.reservation_state.value == "held"
    assert result.proposal_id == filed.proposal_id

    # --- the entry cycle turns the held reservation into a fill, on the
    # labelled proof venue's own book — now a second **newer** than the
    # decision, clearing entry.py's book_before_latency guard. ---
    fill_data = StaticSpotMarketData(
        {(proof_venue.EXCHANGE, proof_venue.SYMBOL): _snapshot(FILL_AT)}
    )
    async with tenant_session(db_session_factory, ids["org"], db_role=WORKER_ROLE) as session:
        outcomes = await execute_approved_entries(
            session, wallet=wallet, data=fill_data, now=FILL_AT
        )
    assert [outcome.status for outcome in outcomes] == ["filled"]
