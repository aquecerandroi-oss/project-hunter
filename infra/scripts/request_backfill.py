#!/usr/bin/env python3
"""Ask the collector for the history beta needs — one window at a time.

``beta_v1`` measures thirty days of hourly returns and refuses to be valid
without twenty **unbroken** days ending at the cut. On 2026-09-08 the VPS held
eleven distinct days of ``candles``, so every market's revision would say
``insufficient_history`` forever and admission would answer ``unavailable`` for
every candidate. This script is how the gap gets closed **without giving anyone
a second REST client**: the joint M2 decision gives REST to the market-worker
alone, so what is published here is the same *fact about a window* the scanner
already publishes (``market.backfill.requested``, PIPELINE.md §1b), with the
same deterministic identity, and the collector plans and fetches it under the
budget it already owns.

Three constraints of that contract decide the shape of this script, and none of
them is negotiable from this side:

- **seven days per request.** ``backfill_plan.MAX_REQUEST_MINUTES`` is 10 080
  and a larger window is *truncated to its most recent seven days* — silently
  enough that asking for 31 days in one message would look like it worked and
  deliver a quarter of it. So the range is cut into whole seven-day windows and
  published **newest first**: the recent end is the one the contiguity rule
  needs, and it is the one that must not be behind 24 days of older requests in
  the history tier's queue;
- **the identity is the window.** ``event_id`` is ``uuid5`` over
  ``(stream, market_id, gap_start, gap_end)`` — the same call the scanner makes
  — so running this twice produces one gap, and re-running it after a partial
  fetch is free;
- **the tail must be settled.** The collector clamps a window that reaches past
  the last minute it considers closed and then deliberately does *not* mark the
  request processed. Cutting two minutes off the recent end here (the
  collector's own ``DETECTION_GRACE``) keeps the newest request from being an
  eternal partial.

**Partitions are a real refusal, not a warning.** ``candles`` is partitioned by
month and the consumer refuses a month that has none (``no_partition``). Thirty
days back always crosses at least one month boundary, so the months the range
touches are checked here and named in the output; the cure is
``create_partitions.py --months-behind N``, which is a different job's work.

Publishing goes through the **outbox**: rows land in ``outbox_events`` inside one
transaction and any running worker's dispatcher puts them on the stream within
about a second. ``--publish`` sweeps the outbox from here instead, for the case
where nothing is running — it publishes whatever else is pending too, which is
what a dispatcher does and is safe by at-least-once.

**``--kind funding`` (T3.7c)** publishes a different shape of request; see
``backfill_funding.py`` for why and how it differs from the candles path above.

Usage:
    uv run python infra/scripts/request_backfill.py --days 31 --dry-run
    uv run python infra/scripts/request_backfill.py --days 31
    uv run python infra/scripts/request_backfill.py --days 31 --markets BTCUSDT,ETHUSDT
    uv run python infra/scripts/request_backfill.py --days 31 --publish
    uv run python infra/scripts/request_backfill.py --kind funding --days 31 --markets BTCUSDT
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from backfill_funding import envelopes_for as funding_envelopes_for
from backfill_funding import window_for as funding_window_for
from backfill_targets import Target, targets_for
from sqlalchemy import text

from hunter_core.db.session import create_engine, create_session_factory, role_session
from hunter_core.domain.enums import Timeframe
from hunter_core.events.outbox import build_envelope, enqueue_many, event_id_for
from hunter_core.events.streams import Streams
from hunter_core.settings import get_settings

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.events.envelope import EventEnvelope

MAX_REQUEST_MINUTES = 7 * 24 * 60
"""The collector's own ceiling per request (``backfill_plan.MAX_REQUEST_MINUTES``).

Duplicated rather than imported: ``infra/scripts`` does not depend on the
market-worker's package, and this number is part of the *published contract*
(PIPELINE.md §1b item 4), not an implementation detail. If the two ever diverge
the collector still truncates safely — it just does it in the log instead of
here."""

SETTLED_GRACE = timedelta(minutes=2)
"""The collector's ``recovery.DETECTION_GRACE``: minutes newer than this are not
considered closed yet, and a request that names them is planned only partially."""

REASON = "beta_history"
PRODUCER = "infra/scripts/request_backfill.py"
BAR = timedelta(hours=1)
MINUTE = timedelta(minutes=1)

_PARTITION = text("SELECT to_regclass(:name) IS NOT NULL AS present")


@dataclass(frozen=True, slots=True)
class Chunk:
    """One ``[gap_start, gap_end)`` window of one market, inside the ceiling."""

    target: Target
    gap_start: datetime
    gap_end: datetime

    @property
    def minutes(self) -> int:
        return int((self.gap_end - self.gap_start) / MINUTE)


def window_for(now: datetime, days: int) -> tuple[datetime, datetime]:
    """``[start, end)`` the beta needs: ``days`` back, plus the anchor bar.

    The first return of the window needs the close of the bar *before* it
    (``BetaEstimate.input_start``), so the request reaches one bar further back
    than the window it serves. Both ends are floored to the minute, which is the
    unit a candle — and a gap — is counted in.
    """
    end = now.replace(second=0, microsecond=0) - SETTLED_GRACE
    return end - timedelta(days=days) - BAR, end


def chunks_for(target: Target, start: datetime, end: datetime) -> list[Chunk]:
    """Whole seven-day windows covering ``[start, end)``, **newest first**."""
    out: list[Chunk] = []
    cursor = end
    span = timedelta(minutes=MAX_REQUEST_MINUTES)
    while cursor > start:
        chunk_start = max(start, cursor - span)
        out.append(Chunk(target=target, gap_start=chunk_start, gap_end=cursor))
        cursor = chunk_start
    return out


def envelope_for(chunk: Chunk, exchange: str) -> EventEnvelope:
    """The same envelope ``hunter_scanner_worker.backfill`` publishes."""
    payload: dict[str, Any] = {
        "market_id": str(chunk.target.market_id),
        "exchange": exchange,
        "symbol": chunk.target.symbol,
        "timeframe": Timeframe.M1.value,
        "gap_start": chunk.gap_start.isoformat(),
        "gap_end": chunk.gap_end.isoformat(),
        "reason": REASON,
        "requested_by": PRODUCER,
    }
    return build_envelope(
        Streams.MARKET_BACKFILL_REQUESTED,
        event_id_for(
            Streams.MARKET_BACKFILL_REQUESTED,
            chunk.target.market_id,
            chunk.gap_start,
            chunk.gap_end,
        ),
        payload,
        producer=PRODUCER,
        key=f"{exchange}:{chunk.target.symbol}",
    )


async def _missing_partitions(session: AsyncSession, start: datetime, end: datetime) -> list[str]:
    """Months of ``candles_1m`` the range touches that do not exist yet."""
    missing: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        name = f"candles_1m_{year}_{month:02d}"
        if not await session.scalar(_PARTITION, {"name": name}):
            missing.append(name)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return missing


async def plan(
    factory: async_sessionmaker[AsyncSession],
    *,
    exchange: str,
    days: int,
    symbols: Sequence[str] | None,
    now: datetime,
    kind: str = "candles",
) -> tuple[list[Chunk], list[str]]:
    if kind == "funding":
        start, end = funding_window_for(now, days)
        async with role_session(factory, db_role="hunter_worker") as session:
            targets = await targets_for(session, exchange, symbols)
        chunks = [Chunk(target=target, gap_start=start, gap_end=end) for target in targets]
        return chunks, []  # funding_rates is not partitioned -- nothing to warn about
    start, end = window_for(now, days)
    async with role_session(factory, db_role="hunter_worker") as session:
        targets = await targets_for(session, exchange, symbols)
        missing = await _missing_partitions(session, start, end)
    return [chunk for target in targets for chunk in chunks_for(target, start, end)], missing


async def publish(
    factory: async_sessionmaker[AsyncSession],
    chunks: Sequence[Chunk],
    *,
    exchange: str,
    kind: str = "candles",
) -> int:
    """Queue every chunk in one transaction. Returns how many rows were queued.

    One transaction, because the request is one operator decision: either the
    whole range is asked for or none of it is, and ``ON CONFLICT (event_id) DO
    NOTHING`` makes a re-run of the same range a no-op.
    """
    if kind == "funding":
        envelopes = funding_envelopes_for(chunks, exchange, producer=PRODUCER)
    else:
        envelopes = [envelope_for(chunk, exchange) for chunk in chunks]
    async with role_session(factory, db_role="hunter_worker") as session:
        await enqueue_many(session, envelopes)
    return len(envelopes)


async def _run(args: argparse.Namespace) -> int:
    exchange: str = args.exchange
    kind: str = args.kind
    symbols = [item.strip().upper() for item in args.markets.split(",") if item.strip()] or None
    engine = create_engine(get_settings())
    try:
        factory = create_session_factory(engine)
        now = datetime.now(tz=UTC)
        chunks, missing = await plan(
            factory, exchange=exchange, days=args.days, symbols=symbols, now=now, kind=kind
        )
        if not chunks:
            print("no market matched: nothing to request")
            return 1
        start, end = funding_window_for(now, args.days) if kind == "funding" else window_for(
            now, args.days
        )
        markets = sorted({chunk.target.symbol for chunk in chunks})
        print(f"kind    {kind}")
        print(f"window  {start.isoformat()} -> {end.isoformat()}")
        print(f"markets {len(markets)}: {', '.join(markets)}")
        print(
            f"windows {len(chunks)} ({len(chunks) // max(1, len(markets))} per market, newest first)"
        )
        for name in missing:
            print(f"WARNING partition {name} does not exist — those minutes will be refused")
        if args.dry_run:
            for chunk in chunks[: args.show]:
                print(
                    f"[dry-run] {chunk.target.symbol} "
                    f"{chunk.gap_start.isoformat()} -> {chunk.gap_end.isoformat()} "
                    f"({chunk.minutes} min)"
                )
            if len(chunks) > args.show:
                print(f"[dry-run] ... {len(chunks) - args.show} more")
            print(f"[dry-run] {len(chunks)} request(s) would be queued on the outbox")
            return 0
        queued = await publish(factory, chunks, exchange=exchange, kind=kind)
        print(f"{queued} request(s) queued on outbox_events")
        if args.publish:
            from hunter_core.events.outbox import reconcile
            from hunter_core.redis import create_redis

            redis = create_redis(get_settings())
            try:
                sent = await reconcile(redis, factory, db_role="hunter_worker")
            finally:
                await redis.aclose()
            print(f"{sent} outbox row(s) published (the whole pending queue, not only these)")
        return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--days", type=int, default=31, help="days of history to ask for")
    parser.add_argument(
        "--kind",
        choices=["candles", "funding"],
        default="candles",
        help="candles (default, seven-day chunks) or funding (T3.7c, one request per market)",
    )
    parser.add_argument(
        "--markets",
        default="",
        help="comma-separated symbols; default: every monitored perpetual with a spot twin",
    )
    parser.add_argument("--exchange", default="binance", help="exchange code")
    parser.add_argument("--dry-run", action="store_true", help="print what would be requested")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="sweep the outbox here instead of waiting for a worker",
    )
    parser.add_argument(
        "--show", type=int, default=12, help="dry-run lines to print before eliding"
    )
    args = parser.parse_args()
    if args.days < 1:
        print("--days must be >= 1")
        return 2
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
