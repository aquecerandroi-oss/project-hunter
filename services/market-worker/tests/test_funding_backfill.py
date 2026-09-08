"""``kind: funding`` on ``market.backfill.requested`` — T3.7c.

Two 31-day replays produced only 23+2 evaluable outcomes out of 224+341: the
rest carried ``funding_schedule_unknown`` because ``funding_rates`` held only
the live-collected period while the candles reached back a month
(``.claude/state/brief-T3.7c-funding-history-backfill.md``). This lane fetches
and persists that history: one REST call per request, under the funding
history rate-limit bucket the live poller already shares, never overwriting a
row that source wrote first.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select

from hunter_core.db.models.market_data import FundingRate
from hunter_core.db.models.system import OutboxEvent, SystemEvent
from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.events.consume import is_processed
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.produce import publish
from hunter_core.events.streams import DEFAULT_MAXLEN, Streams
from hunter_core.settings import Settings
from hunter_exchanges.base import RateLimited
from hunter_market_worker import backfill
from hunter_market_worker.universe import MonitoredUniverse

from . import builders
from .db_helpers import seed_market
from .fakes import FakeAdapter
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration

MINUTE = timedelta(minutes=1)
STREAM = Streams.MARKET_BACKFILL_REQUESTED


def funding_request_payload(
    *, market_id: Any, exchange: str, symbol: str, gap_start: Any, gap_end: Any, **overrides: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "market_id": str(market_id),
        "exchange": exchange,
        "symbol": symbol,
        "kind": "funding",
        "gap_start": gap_start.isoformat(),
        "gap_end": gap_end.isoformat(),
        "reason": "funding_history",
        "requested_by": "infra/scripts/request_backfill.py",
    }
    payload.update(overrides)
    return payload


async def publish_request(redis: Any, payload: dict[str, Any], *, event_id: Any = None) -> None:
    envelope = EventEnvelope(
        type=STREAM,
        producer="test",
        key=f"{payload['exchange']}:{payload['symbol']}",
        payload=payload,
        **({"event_id": event_id} if event_id is not None else {}),
    )
    await publish(redis, STREAM, envelope, DEFAULT_MAXLEN[STREAM])


def build_consumer(
    session_factory: Any, redis: Any, adapter: Any, symbols: list[str], *, shard: str = "0/1"
) -> backfill.BackfillConsumer:
    universe = MonitoredUniverse()
    universe.set(symbols)
    return backfill.BackfillConsumer(
        session_factory,
        adapter,
        redis,
        universe,
        Settings(market_shard=shard),
        instance="test",
        claim_idle_ms=0,
    )


async def funding_rows(session_factory: Any, market_id: Any) -> list[FundingRate]:
    async with role_session(session_factory, db_role="hunter_worker") as session:
        rows = await session.scalars(
            select(FundingRate)
            .where(FundingRate.market_id == market_id)
            .order_by(FundingRate.funding_time)
        )
        return list(rows)


class RealizedAdapter(FakeAdapter):
    """A fake with a scripted, symbol-keyed realized-funding response."""

    def __init__(self, code: str) -> None:
        super().__init__(code=code)
        self.realized: dict[str, list[Any]] = {}
        self.calls: list[tuple[str, Any, Any]] = []
        self.raise_rate_limited = False

    async def fetch_realized_funding(self, symbol: str, start: Any, end: Any) -> list[Any]:
        self.calls.append((symbol, start, end))
        if self.raise_rate_limited:
            raise RateLimited("no budget", exchange=self.code, retry_after_s=1.0)
        return self.realized.get(symbol, [])


async def test_a_funding_request_lands_settlements_and_announces_completion(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    now = utcnow()
    window_start = now - 31 * 24 * 60 * MINUTE
    settlements = [
        builders.funding("BTCUSDT", exchange=exchange_code, ts=window_start + timedelta(hours=8 * n))
        for n in range(3)
    ]
    adapter = RealizedAdapter(exchange_code)
    adapter.realized["BTCUSDT"] = settlements
    await publish_request(
        redis_client,
        funding_request_payload(
            market_id=market_id,
            exchange=exchange_code,
            symbol="BTCUSDT",
            gap_start=window_start,
            gap_end=now,
        ),
    )
    consumer = build_consumer(db_session_factory, redis_client, adapter, ["BTCUSDT"])

    outcomes = await consumer.run_once()

    assert [outcome.name for outcome in outcomes] == ["accepted"]
    rows = await funding_rows(db_session_factory, market_id)
    assert [row.funding_time for row in rows] == [s.ts for s in settlements]
    assert adapter.calls == [("BTCUSDT", window_start, now)]

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        completed = (
            await session.execute(
                select(OutboxEvent.payload).where(
                    OutboxEvent.stream == Streams.MARKET_FUNDING_BACKFILLED
                )
            )
        ).all()
        derivatives = await session.scalar(
            select(OutboxEvent.id).where(OutboxEvent.stream == Streams.MARKET_DERIVATIVES)
        )
    assert len(completed) == 1
    payload = completed[0][0]["payload"]
    assert payload["count"] == 3
    assert payload["source"] == "rest"
    assert derivatives is not None  # each settlement still announces individually


async def test_a_rerun_of_the_same_window_never_duplicates_rows(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "ETHUSDT")
    now = utcnow()
    window_start = now - 10 * 24 * 60 * MINUTE
    settlement = builders.funding("ETHUSDT", exchange=exchange_code, ts=window_start + timedelta(hours=8))
    adapter = RealizedAdapter(exchange_code)
    adapter.realized["ETHUSDT"] = [settlement]
    payload = funding_request_payload(
        market_id=market_id,
        exchange=exchange_code,
        symbol="ETHUSDT",
        gap_start=window_start,
        gap_end=now,
    )
    consumer = build_consumer(db_session_factory, redis_client, adapter, ["ETHUSDT"])

    await publish_request(redis_client, payload)
    await consumer.run_once()
    first = await funding_rows(db_session_factory, market_id)

    # A different event_id: what is under test is upsert idempotency, not the
    # processed-set guard.
    await publish_request(redis_client, payload, event_id=uuid4())
    await consumer.run_once()
    second = await funding_rows(db_session_factory, market_id)

    assert len(first) == 1
    assert [row.funding_time for row in second] == [row.funding_time for row in first]


async def test_a_backfilled_row_never_overwrites_one_the_live_poller_already_wrote(
    db_session_factory: Any, redis_client: Any
) -> None:
    """The identity is ``(market_id, funding_time)``; ``ON CONFLICT DO NOTHING``
    means whichever source lands first keeps its own rate forever."""
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "SOLUSDT")
    now = utcnow()
    settlement_time = now - 5 * 24 * 60 * MINUTE
    live_rate = builders.funding("SOLUSDT", rate="0.0002", exchange=exchange_code, ts=settlement_time)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        from hunter_market_worker.persist_rows import upsert_funding
        from hunter_market_worker.queues import RealizedFunding

        await upsert_funding(
            session, [RealizedFunding.model_validate(live_rate.model_dump())], {"SOLUSDT": market_id}
        )

    conflicting_rate = live_rate.model_copy(update={"funding_rate": live_rate.funding_rate * 5})
    adapter = RealizedAdapter(exchange_code)
    adapter.realized["SOLUSDT"] = [conflicting_rate]
    await publish_request(
        redis_client,
        funding_request_payload(
            market_id=market_id,
            exchange=exchange_code,
            symbol="SOLUSDT",
            gap_start=settlement_time - MINUTE,
            gap_end=now,
        ),
    )
    consumer = build_consumer(db_session_factory, redis_client, adapter, ["SOLUSDT"])

    outcomes = await consumer.run_once()

    assert [outcome.name for outcome in outcomes] == ["accepted"]
    rows = await funding_rows(db_session_factory, market_id)
    assert len(rows) == 1
    assert rows[0].rate == live_rate.funding_rate  # the live value, untouched


async def test_a_market_outside_the_universe_is_refused(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "AVAXUSDT")
    now = utcnow()
    await publish_request(
        redis_client,
        funding_request_payload(
            market_id=market_id,
            exchange=exchange_code,
            symbol="AVAXUSDT",
            gap_start=now - 10 * 24 * 60 * MINUTE,
            gap_end=now,
        ),
    )
    consumer = build_consumer(
        db_session_factory, redis_client, RealizedAdapter(exchange_code), ["BTCUSDT"]
    )

    outcomes = await consumer.run_once()

    assert [(o.name, o.reason) for o in outcomes] == [("refused", "market_not_monitored")]


async def test_a_future_window_is_refused(db_session_factory: Any, redis_client: Any) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "DOGEUSDT")
    now = utcnow()
    await publish_request(
        redis_client,
        funding_request_payload(
            market_id=market_id,
            exchange=exchange_code,
            symbol="DOGEUSDT",
            gap_start=now + 10 * MINUTE,
            gap_end=now + 70 * MINUTE,
        ),
    )
    consumer = build_consumer(
        db_session_factory, redis_client, RealizedAdapter(exchange_code), ["DOGEUSDT"]
    )

    outcomes = await consumer.run_once()

    assert [(o.name, o.reason) for o in outcomes] == [("refused", "future_window")]


async def test_an_adapter_without_realized_funding_is_refused(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "LINKUSDT")
    now = utcnow()
    await publish_request(
        redis_client,
        funding_request_payload(
            market_id=market_id,
            exchange=exchange_code,
            symbol="LINKUSDT",
            gap_start=now - 10 * 24 * 60 * MINUTE,
            gap_end=now,
        ),
    )
    consumer = build_consumer(
        db_session_factory, redis_client, FakeAdapter(code=exchange_code), ["LINKUSDT"]
    )

    outcomes = await consumer.run_once()

    assert [(o.name, o.reason) for o in outcomes] == [("refused", "funding_unsupported")]


async def test_a_rate_limited_fetch_is_a_system_event_not_a_silent_retry(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "NEARUSDT")
    now = utcnow()
    event_id = uuid4()
    adapter = RealizedAdapter(exchange_code)
    adapter.raise_rate_limited = True
    await publish_request(
        redis_client,
        funding_request_payload(
            market_id=market_id,
            exchange=exchange_code,
            symbol="NEARUSDT",
            gap_start=now - 10 * 24 * 60 * MINUTE,
            gap_end=now,
        ),
        event_id=event_id,
    )
    consumer = build_consumer(db_session_factory, redis_client, adapter, ["NEARUSDT"])

    outcomes = await consumer.run_once()

    assert [(o.name, o.reason) for o in outcomes] == [("refused", "rate_limited")]
    assert not await is_processed(redis_client, consumer.group, str(event_id))
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        events = await session.scalars(
            select(SystemEvent).where(SystemEvent.event == "funding_backfill_rate_limited")
        )
        assert len(list(events)) == 1


async def test_an_unsupported_kind_is_refused_without_touching_the_candle_lane(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "OPUSDT")
    now = utcnow()
    await publish_request(
        redis_client,
        funding_request_payload(
            market_id=market_id,
            exchange=exchange_code,
            symbol="OPUSDT",
            gap_start=now - MINUTE,
            gap_end=now,
            kind="open_interest",
        ),
    )
    consumer = build_consumer(
        db_session_factory, redis_client, RealizedAdapter(exchange_code), ["OPUSDT"]
    )

    outcomes = await consumer.run_once()

    assert [(o.name, o.reason) for o in outcomes] == [("refused", "unsupported_kind")]


async def test_a_malformed_funding_payload_does_not_stop_the_collector(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    await publish_request(
        redis_client, {"exchange": exchange_code, "symbol": "BTCUSDT", "kind": "funding"}
    )
    consumer = build_consumer(
        db_session_factory, redis_client, RealizedAdapter(exchange_code), ["BTCUSDT"]
    )

    outcomes = await consumer.run_once()

    assert [(o.name, o.reason) for o in outcomes] == [("refused", "unreadable_payload")]
