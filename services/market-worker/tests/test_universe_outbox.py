"""``market.universe.changed`` goes through the outbox (T2.9b, PIPELINE.md §10b).

It is a **durable** event by §10b's own criterion — the scanner warms up the
markets it announces and shuts down the ones it retires — and until now it was
the market-worker's last durable producer publishing best-effort: a universe
change that happened while Redis was unavailable was simply lost, and nothing
downstream ever learned that a market had entered or left.

The fix is the same one every other durable producer here already uses: the
event is queued in the very transaction that writes ``is_monitored`` and
``monitor_rank``, and the dispatcher that is already running publishes it. What
these tests pin is that the two really are one transaction, that a Redis outage
between the commit and the ``XADD`` costs nothing but latency, and that the
Shadow Lab's tracking hold — which widens *collection* without widening
*eligibility* — still produces no event of its own.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy import delete, select

from hunter_core.db.models.markets import Market
from hunter_core.db.models.system import OutboxEvent
from hunter_core.db.session import role_session
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.outbox import reconcile
from hunter_core.events.streams import Streams
from hunter_core.settings import Settings
from hunter_market_worker import durable
from hunter_market_worker import universe as universe_mod

from . import builders
from .fakes import FakeAdapter
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration

PRODUCER = "market-worker@test:1"


class DeadRedis:
    """A Redis that is down for every call ``refresh_universe`` makes after
    the commit. Anything reached before it would fail the test for the wrong
    reason, which is exactly what makes this a useful fake."""

    def __getattr__(self, name: str) -> Any:
        async def _boom(*_args: Any, **_kwargs: Any) -> Any:
            raise ConnectionError(f"redis is down ({name})")

        return _boom


def _adapter_with(exchange_code: str, symbols_and_volumes: dict[str, str]) -> FakeAdapter:
    adapter = FakeAdapter(code=exchange_code)
    for symbol, volume in symbols_and_volumes.items():
        base = symbol.removesuffix("USDT")
        adapter.markets.append(builders.market(symbol, base, exchange=exchange_code))
        adapter.tickers[symbol] = builders.ticker(
            symbol, "100", quote_volume_24h=volume, exchange=exchange_code
        )
    return adapter


async def _clear_outbox(factory: Any) -> None:
    async with role_session(factory, db_role="hunter_worker") as session:
        await session.execute(delete(OutboxEvent))


async def _universe_rows(factory: Any) -> list[Any]:
    async with role_session(factory, db_role="hunter_worker") as session:
        rows = await session.execute(
            select(OutboxEvent.event_id, OutboxEvent.payload, OutboxEvent.dispatched_at)
            .where(OutboxEvent.stream == Streams.MARKET_UNIVERSE_CHANGED)
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
        )
        return list(rows.all())


async def _monitored(factory: Any, exchange_code: str) -> set[str]:
    from hunter_core.db.models.markets import Exchange

    async with role_session(factory, db_role="hunter_worker") as session:
        symbols = await session.scalars(
            select(Market.symbol)
            .join(Exchange, Exchange.id == Market.exchange_id)
            .where(Exchange.code == exchange_code, Market.is_monitored.is_(True))
        )
        return set(symbols)


async def test_a_universe_change_is_queued_and_not_published_by_the_producer(
    db_session_factory: Any, redis_client: Any
) -> None:
    """The producer's hot path never touches Redis: it queues and moves on.

    Publishing inline is what made this event losable in the first place, and
    it is also what would let a stalled Redis hold the refresh transaction open
    while it waited on an ``XADD``.
    """
    code = unique_code()
    await _clear_outbox(db_session_factory)
    adapter = _adapter_with(code, {"AUSDT": "300", "BUSDT": "100"})

    await universe_mod.refresh_universe(
        db_session_factory,
        adapter,
        redis_client,
        Settings(market_universe_size=10),
        producer=PRODUCER,
    )

    rows = await _universe_rows(db_session_factory)
    assert len(rows) == 1
    assert rows[0].dispatched_at is None
    assert await redis_client.xlen(Streams.MARKET_UNIVERSE_CHANGED) == 0

    envelope = EventEnvelope.model_validate(rows[0].payload)
    assert envelope.type == Streams.MARKET_UNIVERSE_CHANGED
    assert envelope.producer == PRODUCER
    assert envelope.key == code
    assert envelope.payload == {"added": ["AUSDT", "BUSDT"], "removed": [], "total": 2}


async def test_the_event_and_the_monitored_flags_are_one_transaction(
    db_session_factory: Any, redis_client: Any
) -> None:
    """``is_monitored``/``monitor_rank`` and the announcement of them commit
    together or not at all — the whole reason the outbox exists."""
    code = unique_code()
    await _clear_outbox(db_session_factory)
    adapter = _adapter_with(code, {"AUSDT": "300", "BUSDT": "100"})
    settings = Settings(market_universe_size=1)

    await universe_mod.refresh_universe(
        db_session_factory, adapter, redis_client, settings, producer=PRODUCER
    )

    assert await _monitored(db_session_factory, code) == {"AUSDT"}
    (row,) = await _universe_rows(db_session_factory)
    assert EventEnvelope.model_validate(row.payload).payload["added"] == ["AUSDT"]
    assert row.event_id == durable.universe_event_id(
        code, {"AUSDT"}, EventEnvelope.model_validate(row.payload).ts
    )


async def test_redis_down_between_the_commit_and_the_publication_loses_nothing(
    db_session_factory: Any, redis_client: Any
) -> None:
    """The failure this whole task is about.

    Before, the ``XADD`` was inline: a Redis that was down at this instant meant
    the scanner never learned that a market had entered or left the universe,
    and nothing would ever tell it. Now the refresh commits, the publication is
    owed, and the reconciliation on the next boot (or the next sweep) pays it.
    """
    code = unique_code()
    await _clear_outbox(db_session_factory)
    adapter = _adapter_with(code, {"AUSDT": "300", "BUSDT": "100"})

    with pytest.raises(ConnectionError):
        await universe_mod.refresh_universe(
            db_session_factory,
            adapter,
            cast("Any", DeadRedis()),
            Settings(market_universe_size=10),
            producer=PRODUCER,
        )

    assert await _monitored(db_session_factory, code) == {"AUSDT", "BUSDT"}
    (row,) = await _universe_rows(db_session_factory)
    assert row.dispatched_at is None, "the event is owed, not lost"

    assert await reconcile(redis_client, db_session_factory) == 1

    entries = await redis_client.xrange(Streams.MARKET_UNIVERSE_CHANGED)
    assert len(entries) == 1
    published = EventEnvelope.from_bytes(entries[0][1][b"data"])
    assert published.key == code
    assert published.payload == {"added": ["AUSDT", "BUSDT"], "removed": [], "total": 2}
    (row,) = await _universe_rows(db_session_factory)
    assert row.dispatched_at is not None


async def test_a_refresh_that_changes_nothing_queues_nothing(
    db_session_factory: Any, redis_client: Any
) -> None:
    """The event announces a *change*. A cycle that finds the same set has
    nothing to say, and saying it anyway would make every consumer of this
    stream re-warm the whole universe every fifteen minutes."""
    code = unique_code()
    await _clear_outbox(db_session_factory)
    adapter = _adapter_with(code, {"AUSDT": "300", "BUSDT": "100"})
    settings = Settings(market_universe_size=10)

    await universe_mod.refresh_universe(
        db_session_factory, adapter, redis_client, settings, producer=PRODUCER
    )
    await universe_mod.refresh_universe(
        db_session_factory, adapter, redis_client, settings, producer=PRODUCER
    )

    assert len(await _universe_rows(db_session_factory)) == 1


async def test_a_removal_is_announced_with_the_symbol_that_left(
    db_session_factory: Any, redis_client: Any
) -> None:
    code = unique_code()
    await _clear_outbox(db_session_factory)
    adapter = _adapter_with(code, {"AUSDT": "300", "BUSDT": "100"})
    settings = Settings(market_universe_size=2)
    await universe_mod.refresh_universe(
        db_session_factory, adapter, redis_client, settings, producer=PRODUCER
    )

    await universe_mod.refresh_universe(
        db_session_factory,
        adapter,
        redis_client,
        Settings(market_universe_size=1),
        producer=PRODUCER,
    )

    rows = await _universe_rows(db_session_factory)
    assert len(rows) == 2
    assert EventEnvelope.model_validate(rows[-1].payload).payload == {
        "added": [],
        "removed": ["BUSDT"],
        "total": 1,
    }


async def test_the_tracking_hold_widens_collection_without_announcing_anything(
    db_session_factory: Any, redis_client: Any
) -> None:
    """SHADOW-LAB.md §8 unchanged: a hold keeps a market's candles coming, it
    does not make the market eligible — so it must not touch the event, which
    reports the eligible set. The hold is applied after the refresh, on the
    common path of ``run_universe``, and queues nothing of its own."""
    code = unique_code()
    await _clear_outbox(db_session_factory)
    adapter = _adapter_with(code, {"AUSDT": "300", "BUSDT": "100"})
    settings = Settings(market_universe_size=1)
    monitored = await universe_mod.refresh_universe(
        db_session_factory, adapter, redis_client, settings, producer=PRODUCER
    )
    assert monitored == ["AUSDT"]
    before = await _universe_rows(db_session_factory)

    widened = await universe_mod.with_tracking_holds(
        db_session_factory, adapter, monitored, settings
    )

    assert widened == ["AUSDT"]
    assert await _universe_rows(db_session_factory) == before
    assert EventEnvelope.model_validate(before[-1].payload).payload["total"] == 1
