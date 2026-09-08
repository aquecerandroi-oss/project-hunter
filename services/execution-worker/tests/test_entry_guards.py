"""T3.5b items 1, 7 and 9 — what the order cycle refuses before it spends a fill.

Three refusals, each one a scenario the guardian's review of ``7ecafd2``
reproduced in Postgres:

- **the tenure is a fact, not a decoration.** A proposal approved at 15:30:00
  reserves the wallet's capital until 15:30:30. The cycle of 15:35:00 must not
  execute it — 270 s after the commitment died the wallet's cash, its slot and
  its participation budget were already given back to everybody else;
- **an expiry says why it never got its order**, and "reserved_until reached" is
  not the answer: the useful fact is the input that never arrived
  (``no_book``, ``avg_price_not_collected``, ``book_before_latency``);
- **§11 at the fill.** The organization is blocked *between* the decision and
  the order. The entry is refused by the state re-read in the very transaction
  that would have written the fill, not by the one the decision saw.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import msgpack
import pytest
from sqlalchemy import text

from hunter_core.domain.enums import MarketType, OrderSide, ReservationState
from hunter_core.domain.types import utcnow
from hunter_core.redis import keys
from hunter_exchanges.binance_spot.normalize import AvgPrice
from hunter_execution_worker.avg_price import ExchangeAvgPrice
from hunter_execution_worker.market_data import RedisSpotMarketData, StaticSpotMarketData
from hunter_risk.inputs import MarketIdentity

from .builders import NOW, Tenant, create_tenant, market_identity, open_wallet
from .scenarios import (
    admit_one,
    block_the_organization,
    count_of,
    entry_snapshot,
    no_book_snapshot,
    reservation_of,
    run_entries,
    static,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_codec: Any = msgpack

RESERVED_UNTIL = NOW + timedelta(seconds=30)
"""15:30:30 — the 30 s tenure of ``PIPELINE.md`` §5, on the row itself."""

LATE = NOW + timedelta(minutes=5)
"""15:35:00 — the cycle that must not execute it."""


def _identity(tenant: Tenant) -> MarketIdentity:
    return market_identity(tenant)


async def _expiry_audit(engine: AsyncEngine, proposal_id: object) -> dict[str, object]:
    async with engine.begin() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT metadata FROM audit_logs WHERE entity_id = :id "
                    "AND action = 'proposal.reservation_expired' ORDER BY created_at DESC LIMIT 1"
                ),
                {"id": proposal_id},
            )
        ).one_or_none()
    return {} if row is None else dict(row.metadata)


class TestAnExpiredReservationIsNeverExecuted:
    async def test_the_cycle_five_minutes_late_expires_it_instead_of_filling_it(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await open_wallet(db_session_factory, db_engine, tenant)
        decision = await admit_one(db_session_factory, wallet)
        assert decision.approved
        before = await reservation_of(db_engine, decision.proposal_id)
        # The tenure is stamped from the wall clock inside ``admit``, not from the
        # injected instant, so the assertion is the window and not the microsecond.
        assert RESERVED_UNTIL <= before.reserved_until < NOW + timedelta(seconds=31)

        # A perfectly eligible book, one second old at 15:35:00. Nothing about
        # the market refuses this entry — only the dead reservation does.
        outcomes = await run_entries(
            db_session_factory,
            wallet,
            static(tenant, entry_snapshot(tenant, at=LATE - timedelta(seconds=1))),
            now=LATE,
        )

        assert [outcome.status for outcome in outcomes] == ["expired"]
        after = await reservation_of(db_engine, decision.proposal_id)
        assert after.reservation_state == ReservationState.EXPIRED.value
        # ``status`` is the other axis: the decision does not stop being true
        # when the tenure runs out (DATABASE.md §18.3).
        assert after.status == "approved"
        assert await count_of(db_engine, wallet, "orders") == 0
        assert await count_of(db_engine, wallet, "fills") == 0
        assert await count_of(db_engine, wallet, "positions") == 0

    async def test_the_expiry_records_the_input_that_never_arrived(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await open_wallet(db_session_factory, db_engine, tenant)
        decision = await admit_one(db_session_factory, wallet)

        outcomes = await run_entries(
            db_session_factory,
            wallet,
            static(tenant, no_book_snapshot(tenant, ts=LATE - timedelta(seconds=1))),
            now=LATE,
        )

        assert [(o.status, o.reason) for o in outcomes] == [("expired", "no_book")]
        metadata = await _expiry_audit(db_engine, decision.proposal_id)
        assert "no_book" in str(metadata.get("reason", ""))
        assert str(metadata["reason"]).startswith("reserved_until reached")


class TestTheStateIsReReadInTheTransactionThatWouldFill:
    async def test_an_organization_blocked_after_the_decision_stops_the_order(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await open_wallet(db_session_factory, db_engine, tenant)
        decision = await admit_one(db_session_factory, wallet)
        assert decision.approved

        await block_the_organization(db_engine, wallet, now=NOW + timedelta(seconds=1))

        outcomes = await run_entries(
            db_session_factory,
            wallet,
            static(tenant, entry_snapshot(tenant)),
            now=NOW + timedelta(seconds=2),
        )

        assert [(o.status, o.reason) for o in outcomes] == [
            ("blocked", "kill_switch_blocks_entries")
        ]
        assert await count_of(db_engine, wallet, "orders") == 0
        assert await count_of(db_engine, wallet, "fills") == 0
        assert await count_of(db_engine, wallet, "positions") == 0
        # The reservation is left standing: releasing pendings is the kill
        # switch cycle's own act, audited as such (RISK_ENGINE.md §5).
        assert (await reservation_of(db_engine, decision.proposal_id)).reservation_state == (
            ReservationState.HELD.value
        )


class TestTheTenureIsReadFromTheRow:
    async def test_a_reservation_still_inside_its_tenure_is_executed_normally(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """The guard must refuse the dead reservation and nothing else."""
        tenant = await create_tenant(db_engine)
        wallet = await open_wallet(db_session_factory, db_engine, tenant)
        decision = await admit_one(db_session_factory, wallet)

        outcomes = await run_entries(
            db_session_factory,
            wallet,
            static(tenant, entry_snapshot(tenant, at=NOW + timedelta(seconds=29))),
            now=NOW + timedelta(seconds=29),
        )

        assert [outcome.status for outcome in outcomes] == ["filled"]
        assert (await reservation_of(db_engine, decision.proposal_id)).reservation_state == (
            ReservationState.CONSUMED.value
        )
        assert await count_of(db_engine, wallet, "positions") == 1


class _HotState:
    """A **labelled double** of the market-worker's spot keys: real msgpack, the
    real payload shape (``proof/run_proof.py``), and no Redis at all.

    It exists so the race can be met through :class:`RedisSpotMarketData` — the
    class that actually stamps ``avg_price_ts`` — instead of through a snapshot
    handed over ready-made, which is the very stamping this test is about.
    """

    def __init__(self, tenant: Tenant, *, at: datetime, price: Decimal = Decimal(100)) -> None:
        self.book_key = keys.book(tenant.slug, tenant.symbol, MarketType.SPOT)
        self.trades_key = keys.trades(tenant.slug, tenant.symbol, MarketType.SPOT)
        self.book = cast(
            "bytes",
            _codec.packb(
                {
                    "ts": at.isoformat(),
                    "bids": [[str(price), "1000"]],
                    "asks": [[str(price), "1000"]],
                },
                use_bin_type=True,
            ),
        )
        self.trade = cast(
            "bytes",
            _codec.packb(
                {
                    "ts": at.isoformat(),
                    "price": str(price),
                    "qty": "1",
                    "side": OrderSide.BUY.value,
                    "trade_id": "1",
                },
                use_bin_type=True,
            ),
        )

    async def get(self, key: str) -> bytes | None:
        return self.book if key == self.book_key else None

    async def lrange(self, key: str, start: int, end: int) -> list[bytes]:
        return [self.trade] if key == self.trades_key else []


class _AvgPriceExchange:
    """A **labelled double** for ``GET /api/v3/avgPrice`` — no HTTP at all."""

    def __init__(self, price: Decimal = Decimal(100)) -> None:
        self.price = price
        self.calls = 0

    async def fetch_avg_price(self, symbol: str) -> AvgPrice:
        self.calls += 1
        return AvgPrice(symbol=symbol, price=self.price, mins=5)


class TestTheCycleClockAndTheReadersStampDoNotRace:
    """T3.29b, finding 1. ``Cycles.entries()`` captures ``now`` and only
    afterwards assembles the snapshot, so the ``avgPrice`` reader's receipt
    instant is **later** than the instant the entry is judged against — on every
    cache miss, which is once per refresh window per market. Reading that
    negative age as "a stamp from the future" deferred an entry on a price
    fetched milliseconds earlier, and it kept deferring until the 30 s
    reservation expired.

    **O que refuta:** the pre-T3.29b bound, which turns this fill into a
    deferral; and any fix that stops measuring the reference's age at all.
    """

    async def test_a_reference_fetched_during_the_pass_fills_instead_of_deferring(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # The wallet, its day anchor and the decision all live on the **real**
        # clock: that is the only way the reader's own ``utcnow()`` can land
        # after the cycle's, which is the whole scenario.
        started = utcnow() - timedelta(seconds=1)
        tenant = await create_tenant(db_engine)
        wallet = await open_wallet(db_session_factory, db_engine, tenant, as_of=started)
        decision = await admit_one(db_session_factory, wallet, now=started)
        assert decision.approved, decision.decision.rejection_reasons

        now = utcnow()  # exactly what ``Cycles.entries()`` reads, before the snapshot
        exchange = _AvgPriceExchange()
        data = RedisSpotMarketData(
            cast("Any", _HotState(tenant, at=now)),
            avg_price=ExchangeAvgPrice(exchange),  # the real wall clock, as in production
        )
        snapshot = await data.snapshot(_identity(tenant))
        assert snapshot.avg_price_ts is not None
        assert snapshot.avg_price_ts >= now

        outcomes = await run_entries(db_session_factory, wallet, cast("Any", data), now=now)
        assert [(o.status, o.reason) for o in outcomes] == [("filled", "")], [
            (o.status, o.reason) for o in outcomes
        ]
        assert await count_of(db_engine, wallet, "positions") == 1


class TestAReferenceWithNoStampIsRefusedEndToEnd:
    """T3.29b, finding 4. ``StaticSpotMarketData`` stamps an undated reference
    with the book's own receipt, which is right for a fixture that hands one
    instant — and is also why no test could reach ``avg_price_undated`` through
    the double. The opt-out makes the absence expressible, so the rule of §7
    ("a price with no stamp is not a reference") is proved through the same
    cycle that would have filled.

    **O que refuta:** a double whose stamping cannot be turned off, and a cycle
    that fills against a reference it cannot age.
    """

    async def test_the_same_snapshot_fills_when_the_double_stamps_it(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await open_wallet(db_session_factory, db_engine, tenant)
        await admit_one(db_session_factory, wallet)
        data = static(tenant, entry_snapshot(tenant))
        outcomes = await run_entries(db_session_factory, wallet, data)
        assert [outcome.status for outcome in outcomes] == ["filled"]

    async def test_with_the_stamp_opted_out_the_entry_defers_undated(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await open_wallet(db_session_factory, db_engine, tenant)
        await admit_one(db_session_factory, wallet)
        unstamped = StaticSpotMarketData(
            {(tenant.slug, tenant.symbol): entry_snapshot(tenant)}, stamp_avg_price=False
        )
        snapshot = await unstamped.snapshot(_identity(tenant))
        assert snapshot.avg_price is not None
        assert snapshot.avg_price_ts is None

        outcomes = await run_entries(db_session_factory, wallet, unstamped)
        assert [(o.status, o.reason) for o in outcomes] == [("deferred", "avg_price_undated")]
        assert await count_of(db_engine, wallet, "orders") == 0
        assert await count_of(db_engine, wallet, "positions") == 0
