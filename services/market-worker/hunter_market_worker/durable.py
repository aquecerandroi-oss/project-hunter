"""Which market events are durable, and the identity each one carries (T2.9).

**The criterion is "does anyone persist an effect from it".** A closed candle,
a realized funding settlement, an open-interest reading, a liquidation and a
change of the monitored universe each become a row — or a subscription, or a
shutdown — somewhere downstream, so losing the event loses work nobody can
reconstruct from Redis. They go through the outbox, queued in the very
transaction that persists the market-data row. ``market.ticks``, the
``rt:*`` pub/sub fan-out and the WS funding *estimate* are the opposite: they
are a view of the present, superseded by the next message within seconds and
persisted by no one, so they keep publishing directly and a lost one costs a
refresh.

Every ``event_id`` here is derived from the persisted row's own natural key, so
the same candle re-delivered by the exchange, retried by the flush loop or
backfilled over REST is one event forever. The enqueue functions are called
from inside ``persist_rows``' upserts — the *shared* path — so a producer
cannot forget them: the REST backfill in ``recovery.py`` announces its candles
through exactly the same code as the WS ingest.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING, Any
from uuid import UUID

from hunter_core.domain.market import to_wire
from hunter_core.events.outbox import build_envelope, enqueue_many, event_id_for
from hunter_core.events.streams import Streams
from hunter_market_worker.publication import liquidation_id

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.domain.market import (
        NormalizedCandle,
        NormalizedFunding,
        NormalizedLiquidation,
        NormalizedOpenInterest,
    )

PRODUCER = "market-worker"
"""Service-level producer name, and the default.

The WS flush path passes the instance-scoped ``market-worker@{instance}``
(``drain_loop`` -> ``persist_batch`` -> the ``upsert_*``). The REST backfill in
``recovery.py`` does **not**: it has no runtime in scope, so its candles are
announced under this name. Only ``producer`` differs — ``event_id`` is derived
from the candle's natural key, so a minute backfilled over REST and the same
minute seen over the WS are one event either way. Threading the instance
through the recovery chain is a follow-up (notes-T2.9.md); until then an
operator reading ``producer`` sees "market-worker" for backfilled minutes and
cannot tell which shard recovered them."""

__all__ = [
    "PRODUCER",
    "candle_event_id",
    "enqueue_candles",
    "enqueue_liquidations",
    "enqueue_open_interest",
    "enqueue_realized_funding",
    "enqueue_universe_changed",
    "funding_event_id",
    "open_interest_event_id",
    "universe_event_id",
]


def _key(exchange: str, symbol: str) -> str:
    return f"{exchange}:{symbol}"


def candle_event_id(candle: NormalizedCandle) -> UUID:
    """Identity of one closed candle = its ``candles`` natural key."""
    return event_id_for(
        Streams.MARKET_CANDLES_CLOSED,
        candle.exchange,
        candle.symbol,
        candle.timeframe.value,
        candle.open_time,
    )


def funding_event_id(funding: NormalizedFunding) -> UUID:
    """Identity of one realized settlement = its ``funding_rates`` natural key."""
    return event_id_for(
        Streams.MARKET_DERIVATIVES, "funding", funding.exchange, funding.symbol, funding.ts
    )


def open_interest_event_id(oi: NormalizedOpenInterest, bucket: datetime) -> UUID:
    """Identity of one OI reading = the 5-minute slot it was persisted in.

    The bucket, not ``oi.ts``: two readings inside one slot collapse to a
    single ``open_interest_history`` row, so they must collapse to a single
    event too.
    """
    return event_id_for(Streams.MARKET_DERIVATIVES, "oi", oi.exchange, oi.symbol, bucket)


async def enqueue_candles(
    session: AsyncSession, candles: list[NormalizedCandle], *, producer: str = PRODUCER
) -> None:
    """Queue ``market.candles.closed`` for candles this transaction inserted.

    One statement for the whole flush, not one per candle: a minute boundary
    closes every monitored market at once, and 200 individual round trips
    inside the flush transaction were measured pushing the persist queue's
    readiness red on the local stack.
    """
    await enqueue_many(
        session,
        [
            build_envelope(
                Streams.MARKET_CANDLES_CLOSED,
                candle_event_id(candle),
                to_wire(candle),
                producer=producer,
                key=_key(candle.exchange, candle.symbol),
            )
            for candle in candles
        ],
    )


def _derivatives_payload(
    exchange: str,
    symbol: str,
    ts: datetime,
    *,
    funding: NormalizedFunding | None = None,
    oi: NormalizedOpenInterest | None = None,
    bucket: datetime | None = None,
    funding_kind: str | None = None,
) -> dict[str, Any]:
    """The ``market.derivatives`` payload, shaped exactly like the ephemeral one.

    ``funding_kind`` is explicit on every derivatives event (Astra, T2.9 round
    1): the stream carries both durable readings and the WS estimate, and a
    consumer must be able to tell which it is holding without inferring it from
    which fields happen to be set.
    """
    return {
        "exchange": exchange,
        "symbol": symbol,
        "open_interest": str(oi.open_interest) if oi else None,
        "open_interest_value": (
            str(oi.open_interest_value) if oi and oi.open_interest_value is not None else None
        ),
        "funding_rate": str(funding.funding_rate) if funding else None,
        "next_funding_time": (
            funding.next_funding_time.isoformat() if funding and funding.next_funding_time else None
        ),
        "mark_price": str(funding.mark_price) if funding else None,
        "index_price": (
            str(funding.index_price) if funding and funding.index_price is not None else None
        ),
        "funding_kind": funding_kind,
        "bucket_ts": bucket.isoformat() if bucket is not None else None,
        "ts": ts.isoformat(),
    }


async def enqueue_realized_funding(
    session: AsyncSession, items: list[NormalizedFunding], *, producer: str = PRODUCER
) -> None:
    """Queue ``market.derivatives`` for settlements this transaction inserted."""
    await enqueue_many(
        session,
        [
            build_envelope(
                Streams.MARKET_DERIVATIVES,
                funding_event_id(funding),
                _derivatives_payload(
                    funding.exchange,
                    funding.symbol,
                    funding.ts,
                    funding=funding,
                    funding_kind="realized",
                ),
                producer=producer,
                key=_key(funding.exchange, funding.symbol),
            )
            for funding in items
        ],
    )


async def enqueue_open_interest(
    session: AsyncSession,
    readings: list[tuple[NormalizedOpenInterest, datetime]],
    *,
    producer: str = PRODUCER,
) -> None:
    """Queue ``market.derivatives`` for OI rows this transaction inserted."""
    await enqueue_many(
        session,
        [
            build_envelope(
                Streams.MARKET_DERIVATIVES,
                open_interest_event_id(oi, bucket),
                _derivatives_payload(oi.exchange, oi.symbol, oi.ts, oi=oi, bucket=bucket),
                producer=producer,
                key=_key(oi.exchange, oi.symbol),
            )
            for oi, bucket in readings
        ],
    )


async def enqueue_liquidations(
    session: AsyncSession, items: list[NormalizedLiquidation], *, producer: str = PRODUCER
) -> None:
    """Queue ``market.liquidations`` for rows this transaction inserted.

    The ``event_id`` is :func:`~hunter_market_worker.publication.liquidation_id`
    — the same uuid5 that is the row's primary key. One identity end to end,
    which is what makes a redelivery recognizable to every consumer.
    """
    await enqueue_many(
        session,
        [
            build_envelope(
                Streams.MARKET_LIQUIDATIONS,
                liquidation_id(liq),
                to_wire(liq),
                producer=producer,
                key=_key(liq.exchange, liq.symbol),
            )
            for liq in items
        ],
    )


def universe_event_id(exchange: str, monitored: Collection[str], at: datetime) -> UUID:
    """Identity of one universe change = exchange + the new set + the instant.

    There is no business row to derive this from — the change *is* the
    difference between two sets — so all three parts are needed and each one
    for a different reason:

    - **exchange**, because two exchanges change independently;
    - **the new set**, because it is what the event is *about*, and because it
      is what makes the identity reconstructible by anyone holding the same
      three inputs. Note what does **not** protect against announcing a
      universe twice: the ``ON CONFLICT DO NOTHING`` of the enqueue never fires
      on this path (Astra, T2.9b review). The row is written in the same
      transaction as ``is_monitored``, so a refresh that failed rolled the
      queued row back with it, and a refresh that committed leaves the next one
      comparing the new set against itself — the guard is the
      ``old_monitored != new_monitored`` in ``universe.refresh_universe``, in
      that same transaction, and the conflict clause is only the second lock;
    - **the instant**, because a set is not unique over time: a market that
      leaves and comes back produces ``{A,B}``, ``{A}``, ``{A,B}`` again, and
      without the instant that third event would collide with the first and be
      dropped — the monitored set would then be right in Postgres and wrong in
      every consumer that only ever heard about the removal.

    The instant is captured once per refresh cycle and is also the envelope's
    ``ts``, so the two can never disagree about when the change happened.
    """
    return event_id_for(Streams.MARKET_UNIVERSE_CHANGED, exchange, ",".join(sorted(monitored)), at)


async def enqueue_universe_changed(
    session: AsyncSession,
    *,
    exchange: str,
    old_monitored: set[str],
    new_monitored: set[str],
    at: datetime,
    producer: str = PRODUCER,
) -> dict[str, Any]:
    """Queue ``market.universe.changed`` and return the payload it carries.

    Called from inside the transaction that writes ``is_monitored`` and
    ``monitor_rank``: the set the event describes and the set the database
    holds commit together, so a consumer can never be told about a universe
    that was rolled back, nor be left ignorant of one that was not.

    The payload reports the **eligible** set. The Shadow Lab's tracking hold
    widens what the worker *collects* without widening what is eligible
    (SHADOW-LAB.md §8), and it is applied later, outside this transaction.
    """
    payload: dict[str, Any] = {
        "added": sorted(new_monitored - old_monitored),
        "removed": sorted(old_monitored - new_monitored),
        "total": len(new_monitored),
    }
    await enqueue_many(
        session,
        [
            build_envelope(
                Streams.MARKET_UNIVERSE_CHANGED,
                universe_event_id(exchange, new_monitored, at),
                payload,
                producer=producer,
                key=exchange,
                ts=at,
            )
        ],
    )
    return payload
