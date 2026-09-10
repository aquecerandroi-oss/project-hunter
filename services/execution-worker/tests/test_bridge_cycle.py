"""T3.14 items 3, 4 and 7 — one slot per cycle, in D3's order, then the fill.

The numbers are the closed ones of ``spec-T3.9-verificacoes.md`` §0: 20.000 USDT
of equity, ``entry_ref = 100``, ``stop = 97,5``, so the engine sizes
``qty = 18,518`` and the entry cycle of T3.5 fills exactly that. Nothing here
fabricates a fill: the doubles are a book and a tape, and the real
``PaperExecutionAdapter`` decides what they fill.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import ReservationState
from hunter_execution_worker.bridge import BridgeOutcome, run_bridge_cycle
from hunter_execution_worker.entry import execute_approved_entries
from hunter_execution_worker.market_data import (
    SpotMarketData,
    SpotSnapshot,
    StaticSpotMarketData,
)
from hunter_execution_worker.wallet import WalletRef

from . import shadow_builders as shadow
from .builders import (
    NO_EXIT_COST,
    NOW,
    SecondMarket,
    Tenant,
    Wallet,
    add_market,
    book,
    create_tenant,
    market_identity,
    open_wallet,
    trade,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WORKER_ROLE = "hunter_worker"
BAR = NOW - timedelta(seconds=30)
FILL_AT = NOW + timedelta(seconds=1)
CYCLE_AT = NOW + timedelta(seconds=2)
"""The pass after the fill, still inside the signal's 120 s entry window."""


@dataclass(frozen=True, slots=True)
class Lab:
    """A wallet, its spot market, the perpetual behind it and an active version."""

    tenant: Tenant
    wallet: Wallet
    perp_market_id: uuid.UUID
    version_id: uuid.UUID

    @property
    def ref(self) -> WalletRef:
        return WalletRef(self.tenant.org_id, self.wallet.portfolio_id)


async def _lab(
    factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    *,
    now: datetime = NOW,
    link_profile: bool = True,
) -> Lab:
    tenant = await create_tenant(engine)
    wallet = await open_wallet(factory, engine, tenant, link_profile=link_profile)
    perp_market_id = await shadow.add_perp_market(engine, tenant)
    version_id = await shadow.create_version(engine, active=True, at=BAR)
    await shadow.set_spot_volume(engine, tenant.market_id, volume=Decimal(120_000_000))
    await shadow.create_agent(
        engine,
        organization_id=tenant.org_id,
        workspace_id=tenant.workspace_id,
        portfolio_id=wallet.portfolio_id,
        version_id=version_id,
    )
    await shadow.set_beta(engine, tenant.market_id, as_of=now)
    await shadow.ensure_candle_partitions(engine, now)
    await shadow.seed_minute_volumes(engine, tenant.market_id, now=now)
    return Lab(tenant, wallet, perp_market_id, version_id)


def _data(
    lab: Lab,
    *,
    received_at: datetime = NOW,
    extra: dict[tuple[str, str], SpotSnapshot] | None = None,
) -> StaticSpotMarketData:
    """A deep, flat book and one fresh print on the wallet's spot market."""
    snapshots: dict[tuple[str, str], SpotSnapshot] = {
        (lab.tenant.slug, lab.tenant.symbol): SpotSnapshot(
            market=market_identity(lab.tenant),
            book=book(lab.tenant, received_at=received_at),
            trades=(trade(lab.tenant, price=Decimal(100), ts=received_at, trade_id=1),),
            avg_price=Decimal(100),
        )
    }
    if extra:
        snapshots.update(extra)
    return StaticSpotMarketData(snapshots)


async def _cycle(
    factory: async_sessionmaker[AsyncSession],
    lab: Lab,
    data: SpotMarketData,
    *,
    now: datetime = NOW,
) -> BridgeOutcome:
    async with tenant_session(factory, lab.tenant.org_id, db_role=WORKER_ROLE) as session:
        return await run_bridge_cycle(
            session, wallet=lab.ref, data=data, now=now, exit_cost_rate=NO_EXIT_COST
        )


async def test_one_signal_becomes_one_approved_proposal_holding_a_reservation(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    lab = await _lab(db_session_factory, db_engine)
    signal_id = await shadow.emit_signal(
        db_engine,
        version_id=lab.version_id,
        market_id=lab.perp_market_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_PAPER,
    )
    outcome = await _cycle(db_session_factory, lab, _data(lab))
    assert outcome.deferred is None, outcome.deferred
    assert outcome.submitted is not None
    assert outcome.submitted.approved, outcome.submitted.decision.rejection_reasons
    assert outcome.submitted.reservation_state is ReservationState.HELD
    assert outcome.signal_id == signal_id

    async with db_engine.begin() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT signal_id, source::text AS source, agent_id, idempotency_key, "
                    "reservation_state::text AS reservation, request_payload FROM trade_proposals "
                    "WHERE portfolio_id = :pf"
                ),
                {"pf": lab.wallet.portfolio_id},
            )
        ).all()
    assert len(row) == 1
    assert row[0].signal_id == signal_id
    assert row[0].source == "agent"
    assert row[0].agent_id is not None
    assert row[0].idempotency_key == f"agent:shadow:{signal_id}"
    assert row[0].reservation == "held"
    # T3.5c item 6: the bridge passes the signal's own target through to the
    # archived geometry — ``shadow.emit_signal`` defaults it to "105".
    assert row[0].request_payload["target"] == "105"


async def test_the_entry_cycle_of_t35_picks_the_bridge_proposal_up_next_cycle(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """Item 7: the reservation the bridge created becomes a real fill, once."""
    lab = await _lab(db_session_factory, db_engine)
    await shadow.emit_signal(
        db_engine,
        version_id=lab.version_id,
        market_id=lab.perp_market_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_PAPER,
    )
    outcome = await _cycle(db_session_factory, lab, _data(lab))
    assert outcome.submitted is not None and outcome.submitted.approved

    data = _data(lab, received_at=FILL_AT)
    async with tenant_session(db_session_factory, lab.tenant.org_id, db_role=WORKER_ROLE) as s:
        outcomes = await execute_approved_entries(s, wallet=lab.ref, data=data, now=FILL_AT)
    assert [item.status for item in outcomes] == ["filled"]

    async with db_engine.begin() as connection:
        position = (
            await connection.execute(
                text("SELECT qty, market_id FROM positions WHERE portfolio_id = :pf"),
                {"pf": lab.wallet.portfolio_id},
            )
        ).one()
    assert position.market_id == lab.tenant.market_id
    assert position.qty > 0


async def test_three_signals_in_one_cycle_submit_the_highest_score_and_the_rest_wait(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """D3 key 1: the Radar score of the perpetual at the source bar decides."""
    lab = await _lab(db_session_factory, db_engine)
    second = await add_market(db_engine, lab.tenant, suffix="B")
    third = await add_market(db_engine, lab.tenant, suffix="C")
    markets = [(lab.tenant.market_id, lab.tenant.symbol), (second.market_id, second.symbol)]
    markets.append((third.market_id, third.symbol))
    perps: list[uuid.UUID] = []
    for index, (spot_market_id, _symbol) in enumerate(markets):
        await shadow.set_spot_volume(db_engine, spot_market_id, volume=Decimal(120_000_000))
        await shadow.set_beta(db_engine, spot_market_id, as_of=NOW)
        await shadow.seed_minute_volumes(db_engine, spot_market_id, now=NOW)
        perp_id = (
            lab.perp_market_id
            if spot_market_id == lab.tenant.market_id
            else await shadow.add_perp_market_for(db_engine, lab.tenant, spot_market_id)
        )
        perps.append(perp_id)
        # 10 / 90 / 50: the middle market is the one that must win.
        await shadow.set_opportunity(
            db_engine,
            perp_id,
            score=[Decimal(10), Decimal(90), Decimal(50)][index],
            last_updated_at=BAR - timedelta(seconds=1),
        )
    signals = [
        await shadow.emit_signal(
            db_engine,
            version_id=lab.version_id,
            market_id=perp_id,
            source_bar_close=BAR,
            emitted_at=BAR + timedelta(seconds=index + 1),
            purpose=shadow.PURPOSE_PAPER,
        )
        for index, perp_id in enumerate(perps)
    ]
    extra = {
        (lab.tenant.slug, symbol): SpotSnapshot(
            market=market_identity(lab.tenant).model_copy(update={"symbol": symbol}),
            book=book(lab.tenant, received_at=NOW),
            trades=(trade(lab.tenant, price=Decimal(100), ts=NOW, trade_id=1),),
            avg_price=Decimal(100),
        )
        for _market_id, symbol in markets
    }
    outcome = await _cycle(db_session_factory, lab, _data(lab, extra=extra))
    assert outcome.candidates == 3
    assert outcome.waiting == 2
    assert outcome.signal_id == signals[1], "the score of 90 has to win"
    assert outcome.refusals == [], "the two runners-up wait, they are not refused"

    async with db_engine.begin() as connection:
        rows = (
            await connection.execute(
                text("SELECT signal_id FROM trade_proposals WHERE portfolio_id = :pf"),
                {"pf": lab.wallet.portfolio_id},
            )
        ).all()
    assert [row.signal_id for row in rows] == [signals[1]]

    # T3.14b review item 2: the next cycle still sees both runners-up — neither
    # was refused, so the durable queue (a query, not memory) reads them again
    # — and this time the second-highest score (50) wins the one slot.
    second_cycle = await _cycle(
        db_session_factory, lab, _data(lab, extra=extra), now=NOW + timedelta(seconds=1)
    )
    assert second_cycle.candidates == 2
    assert second_cycle.waiting == 1
    assert second_cycle.signal_id == signals[2], "the score of 50 wins the second slot"
    assert second_cycle.refusals == []

    async with db_engine.begin() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT signal_id FROM trade_proposals WHERE portfolio_id = :pf ORDER BY created_at"
                ),
                {"pf": lab.wallet.portfolio_id},
            )
        ).all()
    assert [row.signal_id for row in rows] == [signals[1], signals[2]]


async def test_a_second_cycle_does_not_file_the_same_signal_twice(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """Running the cycle again is a no-op: the signal already has a proposal."""
    lab = await _lab(db_session_factory, db_engine)
    await shadow.emit_signal(
        db_engine,
        version_id=lab.version_id,
        market_id=lab.perp_market_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_PAPER,
    )
    first = await _cycle(db_session_factory, lab, _data(lab))
    assert first.submitted is not None
    second = await _cycle(db_session_factory, lab, _data(lab), now=NOW + timedelta(seconds=5))
    assert second.submitted is None
    assert second.candidates == 0

    async with db_engine.begin() as connection:
        count = await connection.scalar(
            text("SELECT count(*) FROM trade_proposals WHERE portfolio_id = :pf"),
            {"pf": lab.wallet.portfolio_id},
        )
    assert count == 1


async def test_without_a_usable_book_the_slot_is_deferred_and_nothing_is_written(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """No fabricated picture: the candidate stays eligible for the next cycle."""
    lab = await _lab(db_session_factory, db_engine)
    await shadow.emit_signal(
        db_engine,
        version_id=lab.version_id,
        market_id=lab.perp_market_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_PAPER,
    )
    empty = StaticSpotMarketData({})
    outcome = await _cycle(db_session_factory, lab, empty)
    assert outcome.candidates == 1
    assert outcome.submitted is None
    assert outcome.deferred == "spot_price_unavailable"

    async with db_engine.begin() as connection:
        count = await connection.scalar(
            text("SELECT count(*) FROM trade_proposals WHERE portfolio_id = :pf"),
            {"pf": lab.wallet.portfolio_id},
        )
    assert count == 0


async def test_a_scaled_perpetual_within_band_is_approved_at_the_spot_scale(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """T3.14b review item 4, case 1: ``1000SHIBUSDT``-shaped perpetual, mapped to
    the spot pair and scaled correctly, sizes exactly like the unscaled
    contract (spot at 100, scaled ``entry_ref``/``stop`` of 100/97,5)."""
    lab = await _lab(db_session_factory, db_engine)
    scaled_perp_id = await shadow.add_scaled_perp_market(db_engine, lab.tenant, scale=1000)
    signal_id = await shadow.emit_signal(
        db_engine,
        version_id=lab.version_id,
        market_id=scaled_perp_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_PAPER,
        entry_ref=Decimal(100_000),
        stop=Decimal(97_500),
        target=Decimal(105_000),
    )
    outcome = await _cycle(db_session_factory, lab, _data(lab))
    assert outcome.deferred is None, outcome.deferred
    assert outcome.submitted is not None
    assert outcome.submitted.approved, outcome.submitted.decision.rejection_reasons
    assert outcome.submitted.reservation_state is ReservationState.HELD
    assert outcome.signal_id == signal_id

    async with db_engine.begin() as connection:
        row = (
            await connection.execute(
                text("SELECT request_payload FROM trade_proposals WHERE portfolio_id = :pf"),
                {"pf": lab.wallet.portfolio_id},
            )
        ).one()
    assert Decimal(row.request_payload["entry_ref"]) == Decimal(100)
    assert Decimal(row.request_payload["stop"]) == Decimal("97.5")
    assert Decimal(row.request_payload["target"]) == Decimal(105)


async def test_a_scaled_perpetual_out_of_band_is_rejected_by_the_risk_engine_with_no_reservation(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """T3.14b review item 4, case 2: correctly mapped and scaled, but the
    signal's own reference (scaled to 150) is nowhere near what spot last
    traded (100) — the Risk Engine's ``signal_validity`` check
    (``max_entry_deviation_pct`` = 0,5 %, ``docs/RISK_ENGINE.md`` §2) refuses
    it, and nothing is reserved. The bridge did not need its own copy of that
    check: mapping and scaling correctly is enough for the existing engine to
    catch a reference that is three orders of magnitude off if the scale is
    ever wrong."""
    lab = await _lab(db_session_factory, db_engine)
    scaled_perp_id = await shadow.add_scaled_perp_market(db_engine, lab.tenant, scale=1000)
    await shadow.emit_signal(
        db_engine,
        version_id=lab.version_id,
        market_id=scaled_perp_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_PAPER,
        entry_ref=Decimal(150_000),  # scales to 150; spot last traded at 100
        stop=Decimal(145_000),
        target=Decimal(160_000),
    )
    outcome = await _cycle(db_session_factory, lab, _data(lab))
    assert outcome.deferred is None, outcome.deferred
    assert outcome.submitted is not None
    assert not outcome.submitted.approved
    assert "signal_validity" in outcome.submitted.decision.rejection_reasons
    assert outcome.submitted.reservation_state is not ReservationState.HELD

    async with db_engine.begin() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT status::text AS status, reservation_state::text AS reservation "
                    "FROM trade_proposals WHERE portfolio_id = :pf"
                ),
                {"pf": lab.wallet.portfolio_id},
            )
        ).one()
    assert row.status == "rejected"
    assert row.reservation != "held"


async def test_a_wallet_it_cannot_price_defers_the_slot_and_admits_it_back_when_marks_return(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """T3.29 item 4, proved on the bridge (T3.29b, finding 2).

    The pre-check lived in ``bridge.py`` with no test of its own, so nothing
    refuted the two ways it could be wrong: never firing (a wallet holding a
    position priced at its last durable mark keeps admitting new entries, with
    equity, drawdown and aggregate risk read off an estimate), and firing for
    ever (an illiquid position freezing the wallet even after the tape came
    back).

    The wallet here holds one filled position. Its market's tape then stops, so
    coverage is 0 of 1: the candidate on a **different** market is *deferred*,
    not refused — nothing is written, the slot is not spent, and the signal is
    read again next cycle. When the tape returns, coverage is 1 of 1 and the same
    candidate is admitted.

    **O que refuta:** a bridge that submits while a held position is marked at
    yesterday's price; a pre-check that rejects instead of deferring (burning a
    signal on a transient tape); a pre-check with no way back.
    """
    lab = await _lab(db_session_factory, db_engine)
    await shadow.emit_signal(
        db_engine,
        version_id=lab.version_id,
        market_id=lab.perp_market_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_PAPER,
    )
    first = await _cycle(db_session_factory, lab, _data(lab))
    assert first.submitted is not None and first.submitted.approved
    async with tenant_session(db_session_factory, lab.tenant.org_id, db_role=WORKER_ROLE) as s:
        outcomes = await execute_approved_entries(
            s, wallet=lab.ref, data=_data(lab, received_at=FILL_AT), now=FILL_AT
        )
    assert [item.status for item in outcomes] == ["filled"]

    # A second market, so the next candidate is not refused as a duplicate of
    # the position the wallet now holds.
    other = await add_market(db_engine, lab.tenant, suffix="M")
    await shadow.set_spot_volume(db_engine, other.market_id, volume=Decimal(120_000_000))
    await shadow.set_beta(db_engine, other.market_id, as_of=NOW)
    await shadow.seed_minute_volumes(db_engine, other.market_id, now=NOW)
    other_perp = await shadow.add_perp_market_for(db_engine, lab.tenant, other.market_id)
    signal_id = await shadow.emit_signal(
        db_engine,
        version_id=lab.version_id,
        market_id=other_perp,
        source_bar_close=BAR,
        emitted_at=BAR + timedelta(seconds=1),
        purpose=shadow.PURPOSE_PAPER,
    )

    # The held market's tape stops an hour back: the marking policy cannot use
    # it, so the wallet's own position has no live price this pass.
    stopped = _two_markets(lab, other, held_trade_at=CYCLE_AT - timedelta(hours=1))
    deferred = await _cycle(db_session_factory, lab, stopped, now=CYCLE_AT)
    assert deferred.candidates == 1
    assert deferred.submitted is None
    assert deferred.deferred == "marks_incomplete"
    assert await _proposals(db_engine, lab) == 1, "nothing was written for the deferred candidate"

    # The tape comes back. Same candidate, same cycle, coverage back to 1.
    recovered = _two_markets(lab, other, held_trade_at=CYCLE_AT)
    admitted = await _cycle(db_session_factory, lab, recovered, now=CYCLE_AT)
    assert admitted.deferred is None, admitted.deferred
    assert admitted.submitted is not None
    assert admitted.signal_id == signal_id
    assert admitted.submitted.approved, admitted.submitted.decision.rejection_reasons
    assert await _proposals(db_engine, lab) == 2


def _two_markets(lab: Lab, other: SecondMarket, *, held_trade_at: datetime) -> StaticSpotMarketData:
    """The wallet's own market with a tape of the caller's choosing, and the
    candidate's market always live — so the only thing the two passes differ in
    is whether the **held position** can be priced."""
    return StaticSpotMarketData(
        {
            (lab.tenant.slug, lab.tenant.symbol): SpotSnapshot(
                market=market_identity(lab.tenant),
                book=book(lab.tenant, received_at=CYCLE_AT),
                trades=(trade(lab.tenant, price=Decimal(100), ts=held_trade_at, trade_id=2),),
                avg_price=Decimal(100),
                avg_price_ts=CYCLE_AT,
            ),
            (lab.tenant.slug, other.symbol): SpotSnapshot(
                market=market_identity(other),
                book=book(lab.tenant, received_at=CYCLE_AT),
                trades=(trade(lab.tenant, price=Decimal(100), ts=CYCLE_AT, trade_id=3),),
                avg_price=Decimal(100),
                avg_price_ts=CYCLE_AT,
            ),
        }
    )


async def _proposals(db_engine: AsyncEngine, lab: Lab) -> int:
    async with db_engine.begin() as connection:
        return int(
            await connection.scalar(
                text("SELECT count(*) FROM trade_proposals WHERE portfolio_id = :pf"),
                {"pf": lab.wallet.portfolio_id},
            )
            or 0
        )


async def test_an_unlinked_risk_profile_defers_the_candidate_and_writes_nothing(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """T3.69b: the bridge admits against the wallet's own limits, and a wallet
    with no linked ``risk_profiles`` row has none — so the candidate is
    **deferred** (nothing written, the 120 s window still running), never
    admitted against the code constant. This is the VPS state before
    ``docs/ACTIVATION.md`` §8b is run."""
    lab = await _lab(db_session_factory, db_engine, link_profile=False)
    await shadow.emit_signal(
        db_engine,
        version_id=lab.version_id,
        market_id=lab.perp_market_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_PAPER,
    )

    outcome = await _cycle(db_session_factory, lab, _data(lab))

    assert outcome.deferred == "risk_profile_missing"
    assert outcome.submitted is None
    async with db_engine.begin() as connection:
        proposals = await connection.scalar(
            text("SELECT count(*) FROM trade_proposals WHERE portfolio_id = :pf"),
            {"pf": lab.wallet.portfolio_id},
        )
    assert proposals == 0
