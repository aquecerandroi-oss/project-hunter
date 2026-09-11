"""T3.86 — the 24 h volume of check 9 is read where ``volume_ts`` is read.

``RISK_ENGINE.md`` §3.1 ("Idade do volume") says the liquidity input carries
**one** stamp for the 24 h figure and for the minute reference, and §7 says no
input is valid for ever. Until this test existed the worker broke both at once:
``quote_volume_24h`` came from ``markets.volume_24h_usd`` — a ticker snapshot
the spot universe refresh rewrites every ``market_universe_refresh_s`` (900 s
by default; measured 296–370 s old on the VPS at 05:37 BRT of 2026-09-11) and
keeps for ever when the symbol drops out of the bulk ticker
(``universe_repo.upsert_markets`` coalesces the old value onto the row) — while
``volume_ts`` was minted from the cycle's own ``now``. The engine then applied
``max_volume_age_s`` (120 s) to a stamp describing the candles and a number
describing something else.

The two tests below are the two halves of that, on the worker's own path: a
24 h figure only the ticker column believes must not buy anything, and a candle
feed that stopped must be refused **by name**, not silently rescued by a fat
number from another instant.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from proof import venue as proof_venue
from sqlalchemy import text

from hunter_core.admission.sources import ProposalRequest
from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import MarketType, OrderSide, TradeDirection
from hunter_core.domain.market import BookLevel, NormalizedOrderBook, NormalizedTrade
from hunter_core.execution.paper import PaperExecutionAdapter
from hunter_core.strategies.envelope import AssumedCosts
from hunter_execution_worker.admission_cycle import decide_requests
from hunter_execution_worker.bridge_inputs import volume_window
from hunter_execution_worker.manual_inputs import manual_request_inputs
from hunter_execution_worker.market_data import SpotSnapshot, StaticSpotMarketData
from hunter_execution_worker.reference import load_market
from hunter_execution_worker.wallet import WalletRef
from hunter_risk.decision import CheckState, RiskDecision

from .shadow_builders import ensure_candle_partitions, seed_minute_volumes, set_beta

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WORKER_ROLE = "hunter_worker"
NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
STALLED_NOW = datetime(2026, 9, 7, 13, 0, tzinfo=UTC)
"""A second instant of its own: ``fx_observations`` is unique per
``(pair, source, observed_at)``, so two wallets opened at the same second
would collide in the fixture rather than in anything this test is about."""
COSTS = AssumedCosts(
    spread_bps=Decimal(2), slippage_bps=Decimal(5), fee_bps=Decimal(4), max_entry_delay_s=60
)
FAT_TICKER = Decimal(120_000_000)
"""What the ticker column says: comfortably over the 50 M floor."""


def _snapshot(at: datetime) -> SpotSnapshot:
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


def _check_state(decision: RiskDecision, name: str) -> tuple[CheckState, str]:
    found = next(check for check in decision.checks if check.name == name)
    return found.state, found.message


async def _set_ticker_volume(engine: AsyncEngine, market_id: uuid.UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE markets SET volume_24h_usd = :v, is_monitored = true WHERE id = :id"),
            {"v": FAT_TICKER, "id": market_id},
        )


async def _decide(
    db_session_factory: async_sessionmaker[AsyncSession],
    *,
    ids: dict[str, uuid.UUID],
    wallet: WalletRef,
    key: str,
    now: datetime = NOW,
) -> RiskDecision:
    """One manual request, decided through the worker's own admission path."""
    data = StaticSpotMarketData({(proof_venue.EXCHANGE, proof_venue.SYMBOL): _snapshot(now)})
    async with tenant_session(db_session_factory, ids["org"], db_role=WORKER_ROLE) as session:
        market = await load_market(session, ids["market"])
        assert market is not None
        inputs = await manual_request_inputs(
            session,
            wallet=wallet,
            market=market,
            data=data,
            policy=PaperExecutionAdapter().policy.marking_policy,
            now=now,
            exit_cost_rate=Decimal(0),
        )
        assert not isinstance(inputs, str), inputs
        request = ProposalRequest(
            client_key=key,
            organization_id=ids["org"],
            portfolio_id=wallet.portfolio_id,
            market_id=ids["market"],
            market=market.identity,
            direction=TradeDirection.LONG,
            entry_ref=proof_venue.ENTRY,
            stop=proof_venue.STOP,
            assumed_costs=COSTS,
            actor_id="t386",
        )
        decided = await decide_requests(
            session, wallet=wallet, requests=[(request, inputs)], now=now
        )
    assert len(decided) == 1
    return decided[0].decision


async def test_the_ticker_column_does_not_decide_the_fifty_million_floor(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A market the candles say is thin is refused while the column says 120 M.

    ``markets.volume_24h_usd`` = 120 M against 31 complete minutes of 1 M in
    the 24 h window = 31 M. Before T3.86 the engine read the column, passed
    check 9 and sized against a market trading a third of the floor.
    """
    ids = await proof_venue.seed(db_engine, "t386-thin", as_of=NOW)
    portfolio_id = await proof_venue.open_wallet(db_session_factory, ids, as_of=NOW)
    wallet = WalletRef(ids["org"], portfolio_id)
    await _set_ticker_volume(db_engine, ids["market"])
    await ensure_candle_partitions(db_engine, NOW)
    await seed_minute_volumes(
        db_engine, ids["market"], now=NOW, quote_volume=Decimal(1_000_000), minutes=31
    )
    await set_beta(db_engine, ids["market"], as_of=NOW)

    decision = await _decide(db_session_factory, ids=ids, wallet=wallet, key="t386-thin-1")

    state, _ = _check_state(decision, "liquidity_24h")
    assert state is CheckState.FAILED
    assert decision.approved is False
    assert "liquidity_24h" in decision.rejection_reasons


async def test_a_stopped_candle_feed_refuses_the_volume_by_name(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The feed stopped ten minutes ago; the ticker column still says 120 M.

    The stamp is the close of the newest candle actually observed, so the
    engine measures 600 s against ``max_volume_age_s`` (120 s) and reports
    ``liquidity_24h`` **unavailable** with the age named — R-OPS-2, instead of
    a silent pass on a number from another instant.
    """
    ids = await proof_venue.seed(db_engine, "t386-stalled", as_of=STALLED_NOW)
    portfolio_id = await proof_venue.open_wallet(db_session_factory, ids, as_of=STALLED_NOW)
    wallet = WalletRef(ids["org"], portfolio_id)
    await _set_ticker_volume(db_engine, ids["market"])
    await ensure_candle_partitions(db_engine, STALLED_NOW)
    stopped_at = STALLED_NOW - timedelta(minutes=10)
    await seed_minute_volumes(db_engine, ids["market"], now=stopped_at, minutes=31)
    await set_beta(db_engine, ids["market"], as_of=STALLED_NOW)

    async with db_session_factory() as session:
        window = await volume_window(session, market_id=ids["market"], now=STALLED_NOW)
    assert window.volume_ts == stopped_at.replace(second=0, microsecond=0)

    decision = await _decide(
        db_session_factory, ids=ids, wallet=wallet, key="t386-stalled-1", now=STALLED_NOW
    )

    state, message = _check_state(decision, "liquidity_24h")
    assert state is CheckState.UNAVAILABLE
    assert "600" in message
    assert decision.approved is False
