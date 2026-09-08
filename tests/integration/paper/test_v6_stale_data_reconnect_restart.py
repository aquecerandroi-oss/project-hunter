"""V6 — stale inputs, reconnections and restarts never produce a silent approval.

**Objetivo (spec V6):** the contract's "fail closed" pattern (§7) survives real
infrastructure — an admission that reads a stale volume or an unobserved book
never approves, and a restarted worker recovers a partially-filled protection
from Postgres alone, never losing or duplicating the remaining quantity.

**Scope note, closed by T3.29 (item 5).** Steps 3 (WS drop with a gap) and 4
(Redis loss mid-decision) were recorded as not deliverable while every test in
this suite used ``StaticSpotMarketData``, which never touches Redis. They are
covered at the end of this module against the **real** ``RedisSpotMarketData``
reading a **real** Redis (the ``redis_container`` fixture of
``tests/integration/conftest.py``), with the hot state written exactly as the
spot collector writes it: one msgpack book under
``mkt:binance:spot:{symbol}:book`` and a newest-first list of prints under
``:trades``. Nothing is doubled between the worker and Redis — the outage is a
closed connection and the gap is a key that is not there.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import msgpack
import pytest
import pytest_asyncio
import redis.asyncio as redis_asyncio

from hunter_core.domain.enums import MarketType
from hunter_core.redis import keys
from hunter_execution_worker.avg_price import AvgPriceQuote, StaticAvgPrice
from hunter_execution_worker.market_data import RedisSpotMarketData, SpotSnapshot
from hunter_risk.inputs import BookLevel, MarketIdentity, MarketLiquidity

from .conftest import (
    HEALTHY_MINUTE,
    NOW,
    admit_entry,
    admit_in,
    at,
    check_of,
    count_rows,
    liquidity_for,
    read_exit_intents,
    read_orders,
    read_positions,
    read_proposal,
    request_for,
    run_entries,
    run_expire_reservations,
    run_protection,
    spot_book,
    spot_trade,
    static_data,
    tenant_session,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from .conftest import Market, Wallet

pytestmark = [pytest.mark.integration]

_codec: Any = msgpack
"""``msgpack`` ships no type information; the execution-worker's own reader
binds it the same way (``market_data._codec``) instead of scattering ignores."""

ENTRY_REF = Decimal(100)
STOP = Decimal("97.5")
WORKER_ROLE = "hunter_worker"


def _fresh_liquidity(
    identity: MarketIdentity,
    *,
    price_ts: datetime,
    book_ts: datetime | None,
    volume_ts: datetime | None,
    asks: tuple[BookLevel, ...],
) -> MarketLiquidity:
    """A liquidity picture with every timestamp named explicitly — never
    ``datetime.now()`` (spec §12 trap 2): a stale test builds a stale input on
    purpose, at an instant it chooses.
    """
    return MarketLiquidity(
        market=identity,
        last_price=Decimal(100),
        mid_price=Decimal(100),
        best_bid=Decimal("99.99"),
        best_ask=Decimal("100.01"),
        price_ts=price_ts,
        asks=asks,
        book_ts=book_ts,
        quote_volume_24h=Decimal(100_000_000),
        last_minute_quote_volume=HEALTHY_MINUTE,
        median_30m_quote_volume=HEALTHY_MINUTE,
        volume_window_complete=True,
        volume_ts=volume_ts,
        gap_state="ok",
        in_universe=True,
    )


class TestAMinuteOldVolumeFortyFiveMinutesAgoNeverApproves:
    """Spec V6 step 1: "volume do minuto de 45 min atrás" — the exact scenario
    already green in the pure core
    (``test_review_findings.py::TestFinding3``); this proves the same
    ``MarketLiquidity`` that would arrive from the admission's own caller (a
    strategy or the manual route) is rejected the same way once it goes
    through ``admit()`` and lands in the persisted decision, not just in the
    engine called directly.

    **O que refuta:** ``approved=True`` with a volume older than
    ``max_volume_age_s`` (120 s, ``paper_v1``); a persisted ``sizing`` computed
    from a stale participation reference; ``liquidity_24h`` reported as
    anything but ``unavailable``.
    """

    async def test_a_volume_stamped_45_minutes_ago_is_unavailable_not_stale_but_ok(
        self, engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        market = wallet.market("SOLUSDT")
        stale_liquidity = _fresh_liquidity(
            market.identity,
            price_ts=NOW,  # the price itself is fresh
            book_ts=NOW,
            volume_ts=at(minutes=-45),  # the volume snapshot is not
            asks=(BookLevel(price=Decimal("100.01"), qty=Decimal(10_000)),),
        )
        request = request_for(wallet, market, entry_ref=ENTRY_REF, stop=STOP)
        async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
            result = await admit_in(
                session,
                wallet,
                market,
                request,
                now=NOW,
                marks={market.id: ENTRY_REF},
                liquidity=stale_liquidity,
            )
        assert result.approved is False

        row = await read_proposal(engine, result.proposal_id)
        assert row.status == "rejected"
        assert row.risk_decision["sizing"] is None
        liquidity_check = check_of(row.risk_decision, "liquidity_24h")
        assert liquidity_check["state"] == "unavailable"
        assert "45" not in liquidity_check["message"]  # the message names seconds, not minutes
        assert "volume" in liquidity_check["message"]


class TestAnUnobservedBookNeverInventsATimestamp:
    """Spec V6 step 2: SPOT's book carries no exchange clock at all
    (``received_at`` is the only stamp, ``.claude/state/notes-T3.0a.md`` §4);
    at the Risk Engine's own input, the equivalent fact is "the book was not
    observed" (``asks=()``, ``book_ts=None``) — and the check must say
    ``unavailable``, never substitute the price feed's timestamp or a
    plausible number.

    **O que refuta:** ``book_depth`` (or any cap derived from it) reporting a
    value when the book was never observed; the check passing because another
    field (``price_ts``) happened to be fresh.
    """

    async def test_no_book_observed_makes_book_depth_unavailable_not_passed(
        self, engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        market = wallet.market("SOLUSDT")
        no_book_liquidity = _fresh_liquidity(
            market.identity, price_ts=NOW, book_ts=None, volume_ts=NOW, asks=()
        )
        request = request_for(wallet, market, entry_ref=ENTRY_REF, stop=STOP)
        async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
            result = await admit_in(
                session,
                wallet,
                market,
                request,
                now=NOW,
                marks={market.id: ENTRY_REF},
                liquidity=no_book_liquidity,
            )
        assert result.approved is False
        row = await read_proposal(engine, result.proposal_id)
        book_check = check_of(row.risk_decision, "book_depth")
        assert book_check["state"] == "unavailable"
        assert "nao observado" in book_check["message"] or "não observado" in book_check["message"]


class TestARestartRecoversAPartiallyFilledProtectionFromPostgresAlone:
    """Spec V6 step 5: kill the process between the stop's partial fill (4 of
    10 vendable that cycle) and the new attempt for the rest — "never a
    position of six units silently unprotected".

    The "restart" is what ``services/execution-worker/tests
    /test_restart_recovery.py`` already established as the honest one (§12
    trap 7): every object this test built is dropped, and a **fresh**
    ``run_protection`` call — no carried-over ``TriggerWatermarks`` or
    ``DegradedRetries``, exactly what a new process starts with — rebuilds the
    intention and finishes the job.

    **O que refuta:** the intention ending anything but ``open`` with
    ``filled_qty`` set to what really sold; a second attempt reusing the first
    attempt's ``client_order_id``; the six remaining units left with no live
    intention at all.
    """

    async def test_the_remainder_gets_a_new_attempt_with_its_own_identity(
        self, engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
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
        book_at = fill_at + timedelta(milliseconds=300)
        entries = await run_entries(
            factory,
            wallet,
            static_data(
                market,
                SpotSnapshot(
                    market=market.identity,
                    book=spot_book(market, received_at=book_at, bid=ENTRY_REF, ask=ENTRY_REF),
                    trades=(spot_trade(market, price=ENTRY_REF, ts=fill_at, trade_id=1),),
                    avg_price=ENTRY_REF,
                ),
            ),
            now=fill_at + timedelta(seconds=1),
        )
        assert [o.status for o in entries] == ["filled"]
        net_base = Decimal("18.499482")  # 18,518 x 0,999 — §0/V5's own number

        # Cycle 1: a shallow book gives the stop only 4 of the position it
        # asks for — the literal "um stop de 10 unidades encontra 4
        # vendáveis" of RISK_ENGINE.md §10, on this suite's own quantities.
        stop_at = at(minutes=1)
        shallow_at = stop_at + timedelta(milliseconds=300)
        partial_cycle_at = stop_at + timedelta(seconds=1)
        shallow_depth = Decimal(4)
        partial = await run_protection(
            factory,
            wallet,
            static_data(
                market,
                SpotSnapshot(
                    market=market.identity,
                    book=spot_book(
                        market,
                        received_at=shallow_at,
                        bid=Decimal(95),
                        ask=Decimal("95.05"),
                        qty=shallow_depth,
                    ),
                    trades=(spot_trade(market, price=Decimal(95), ts=stop_at, trade_id=2),),
                    avg_price=ENTRY_REF,
                ),
            ),
            now=partial_cycle_at,
        )
        assert [o.status for o in partial] == ["partially_filled"]

        positions = await read_positions(engine, wallet)
        assert positions[0].qty == net_base - shallow_depth
        intents = await read_exit_intents(engine, wallet)
        assert intents[0].filled_qty == shallow_depth
        assert intents[0].state == "open"  # never closed with 6 units unaccounted
        first_attempt = (await read_orders(engine, wallet))[-1].client_order_id

        # The "restart": a brand-new cycle, no watermarks or backoff carried
        # over from the call above — the process died and came back with
        # nothing in memory (§12 trap 7). It finishes the job with an
        # attempt of its own identity.
        later = partial_cycle_at + timedelta(minutes=1)
        later_book_at = later + timedelta(milliseconds=300)
        later_cycle_at = later + timedelta(seconds=1)
        finished = await run_protection(
            factory,
            wallet,
            static_data(
                market,
                SpotSnapshot(
                    market=market.identity,
                    book=spot_book(
                        market, received_at=later_book_at, bid=Decimal(95), ask=Decimal("95.05")
                    ),
                    trades=(spot_trade(market, price=Decimal(95), ts=later, trade_id=3),),
                    avg_price=ENTRY_REF,
                ),
            ),
            now=later_cycle_at,
        )
        assert [o.status for o in finished] == ["filled"]

        after_positions = await read_positions(engine, wallet)
        after_orders = await read_orders(engine, wallet)
        second_attempt = after_orders[-1].client_order_id
        assert second_attempt != first_attempt  # its own identity, never reused
        assert after_positions[0].status == "closing"  # dust, §T3.5b — not an unprotected loss
        after_intents = await read_exit_intents(engine, wallet)
        assert after_intents[0].filled_qty == net_base - after_positions[0].qty


def _pack_book(*, received_at: datetime, bid: Decimal, ask: Decimal, qty: Decimal) -> bytes:
    """The book exactly as the spot collector writes it (T3.0a §4: no exchange
    clock, ``ts`` is our own receipt)."""
    return cast(
        "bytes",
        _codec.packb(
            {
                "ts": received_at.isoformat(),
                "bids": [[str(bid), str(qty)]],
                "asks": [[str(ask), str(qty)]],
            },
            use_bin_type=True,
        ),
    )


def _pack_trade(*, ts: datetime, price: Decimal, trade_id: int) -> bytes:
    return cast(
        "bytes",
        _codec.packb(
            {
                "ts": ts.isoformat(),
                "trade_id": str(trade_id),
                "price": str(price),
                "qty": "1",
                "side": "buy",
            },
            use_bin_type=True,
        ),
    )


async def _write_hot_state(
    redis: Any, market: Market, *, received_at: datetime, price: Decimal
) -> None:
    await redis.set(
        keys.book("binance", market.symbol, MarketType.SPOT),
        _pack_book(received_at=received_at, bid=price, ask=price, qty=Decimal(10_000)),
    )
    await redis.delete(keys.trades("binance", market.symbol, MarketType.SPOT))
    await redis.lpush(
        keys.trades("binance", market.symbol, MarketType.SPOT),
        _pack_trade(ts=received_at, price=price, trade_id=1),
    )


class _DeadRedis:
    """A **labelled double** for the one failure a container cannot stage on
    demand: the connection is gone *during* the decision, so every read raises.
    Deliberately not a double of the worker — the reader under test is the real
    ``RedisSpotMarketData``, and only its socket is broken."""

    async def get(self, key: str) -> bytes | None:
        raise ConnectionError(f"Error 111 connecting to redis:6379 ({key})")

    async def lrange(self, key: str, start: int, end: int) -> list[bytes]:
        raise ConnectionError(f"Error 111 connecting to redis:6379 ({key})")


@pytest_asyncio.fixture
async def hot_state(pipeline_redis_url: str) -> AsyncIterator[Any]:
    """A real Redis, flushed before and after — the spot collector's hot state."""
    client = cast("Any", redis_asyncio.from_url(pipeline_redis_url))
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


class TestAWsDropLeavesAGapAndTheEntryDefersInsteadOfFilling:
    """Spec V6 step 3, closed by T3.29: the spot socket drops, the book key ages
    out of the hot state and the tape stops advancing. The approved proposal
    must **defer** — nothing written, the attempt not spent — and then lose its
    reservation to the 30 s tenure with the reason named, never fill against the
    last book the collector managed to write before the drop.

    **O que refuta:** an order or a fill written while the book key is gone; a
    stale book (older than the eligibility window) accepted because it is the
    only one there is; a reservation that survives the tenure because the input
    never arrived.
    """

    async def test_the_book_key_disappearing_defers_and_then_expires_the_reservation(
        self,
        engine: AsyncEngine,
        factory: async_sessionmaker[AsyncSession],
        wallet: Wallet,
        hot_state: Any,
    ) -> None:
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
        data = RedisSpotMarketData(hot_state)

        # The socket is down: the collector wrote nothing and the book key that
        # existed has aged out with its TTL. The tape is empty for the same
        # reason — a candle never supplies a retroactive print.
        deferred = await run_entries(factory, wallet, data, now=at(seconds=1))
        assert [(o.status, o.reason) for o in deferred] == [("deferred", "no_book")]
        assert await count_rows(engine, wallet, "orders") == 0
        assert await count_rows(engine, wallet, "fills") == 0
        assert (await read_proposal(engine, decision.proposal_id)).reservation_state == "held"

        # The reservation dies of its own 30 s tenure, released with a reason —
        # never executed late (PIPELINE.md §8: "propostas approved sem ordem
        # apos 30 s perdem a reserva").
        expired = await run_expire_reservations(factory, wallet, now=at(seconds=45))
        assert list(expired) == [decision.proposal_id]
        row = await read_proposal(engine, decision.proposal_id)
        assert row.reservation_state == "expired"
        assert row.status == "approved"  # what the engine decided stays true
        assert await count_rows(engine, wallet, "orders") == 0

    async def test_a_book_written_before_the_gap_is_not_eligible_after_it(
        self,
        engine: AsyncEngine,
        factory: async_sessionmaker[AsyncSession],
        wallet: Wallet,
        hot_state: Any,
    ) -> None:
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
        # The last picture the collector managed to write, then the drop: the
        # cycle runs five minutes later and the key is still that old one. The
        # book is *there* and still refused — ``book_stale`` — and by then the
        # 30 s tenure has run out, so the expiry names the input that never
        # arrived instead of "reserved_until reached".
        await _write_hot_state(hot_state, market, received_at=at(seconds=1), price=ENTRY_REF)
        outcomes = await run_entries(
            factory, wallet, RedisSpotMarketData(hot_state), now=at(minutes=5)
        )
        assert [(o.status, o.reason) for o in outcomes] == [("expired", "book_stale")]
        assert await count_rows(engine, wallet, "fills") == 0
        assert await count_rows(engine, wallet, "orders") == 0
        assert (await read_proposal(engine, decision.proposal_id)).reservation_state == "expired"


class TestRedisGoingAwayMidDecisionWritesNothingAndLosesNothing:
    """Spec V6 step 4, closed by T3.29. The hot state is the only source of a
    fill's two inputs; when it cannot be *read*, the picture is "unread", not
    "empty", and the two must not be confused. The answer is the same and it is
    the safe one: defer, keep the reservation, and finish the entry on a later
    pass once Redis is back — with no second order.

    **O que refuta:** a cycle that raises and takes the whole pass (every other
    wallet's protection included) down over one unreachable key; an order
    written against an empty picture; a lost reservation; a duplicate order when
    the same proposal is executed again after the recovery.
    """

    async def test_the_outage_is_named_in_the_snapshot_not_confused_with_an_empty_book(
        self, wallet: Wallet
    ) -> None:
        market = wallet.market("SOLUSDT")
        snapshot = await RedisSpotMarketData(cast("Any", _DeadRedis())).snapshot(market.identity)
        assert snapshot.book is None
        assert snapshot.trades == ()
        assert "hot_state_unreachable" in snapshot.unavailable
        assert "no_book" in snapshot.unavailable

    async def test_the_entry_defers_through_the_outage_and_completes_after_it(
        self,
        engine: AsyncEngine,
        factory: async_sessionmaker[AsyncSession],
        wallet: Wallet,
        hot_state: Any,
    ) -> None:
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

        # Redis dies exactly while this pass is assembling the picture.
        during = await run_entries(
            factory, wallet, RedisSpotMarketData(cast("Any", _DeadRedis())), now=at(seconds=1)
        )
        # "Unread", not "empty": the reason names the incident, not the symptom.
        assert [(o.status, o.reason) for o in during] == [("deferred", "hot_state_unreachable")]
        assert await count_rows(engine, wallet, "orders") == 0
        assert (await read_proposal(engine, decision.proposal_id)).reservation_state == "held"

        # Redis comes back inside the tenure and the same reservation is spent
        # once — one order, one fill, the attempt never duplicated.
        fill_at = at(seconds=10)
        await _write_hot_state(
            hot_state, market, received_at=fill_at + timedelta(milliseconds=300), price=ENTRY_REF
        )
        quotes = {
            ("binance", market.symbol): AvgPriceQuote(price=ENTRY_REF, mins=5, observed_at=fill_at)
        }
        after = await run_entries(
            factory,
            wallet,
            RedisSpotMarketData(hot_state, avg_price=StaticAvgPrice(quotes)),
            now=fill_at + timedelta(seconds=1),
        )
        assert [o.status for o in after] == ["filled"]
        assert await count_rows(engine, wallet, "orders") == 1
        assert await count_rows(engine, wallet, "fills") == 1
