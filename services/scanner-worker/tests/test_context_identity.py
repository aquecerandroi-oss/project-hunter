"""The incremental context is the rebuilt context, byte for byte.

The acceptance criterion of T2.5c is not the benchmark, it is this: a market
advanced with a cache that survived the tick must produce the **same vector**
as one whose context was rebuilt from the hot state at the same cut. The
benchmark only says why we bothered.

The oracle chain is two links, both tested: ``tests/test_candle_cache.py``
proves a *fresh* cache answers exactly what ``hotstate.decode_candles`` answers
for the rows it is given, and this file proves a *kept* cache answers what a
fresh one does -- over sixty synthetic minutes that include a hole, a backfill
rewriting the middle of the list, a forming candle updated inside the minute,
and the ring buffer sliding at 1500.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest

from hunter_core.domain.market import NormalizedCandle
from hunter_core.redis import keys
from hunter_core.strategies.canonical import canonical_json
from hunter_scanner_worker.baselines import BaselineCache
from hunter_scanner_worker.config import ScannerConfig
from hunter_scanner_worker.context import build_market_context
from hunter_scanner_worker.coverage import read_coverage
from hunter_scanner_worker.hotcache import HotCache
from hunter_scanner_worker.persist import WriteBatch
from hunter_scanner_worker.registry import MarketRef, MarketRegistry
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.state import ScannerState

from .builders import EXCHANGE, ORIGIN, FakeHotState, book_payload, candle, candle_rows, trade_rows
from .policies import build_policy

pytestmark = pytest.mark.unit

SYMBOL = "SYM000USDT"
REF = MarketRef(market_id=UUID(int=7), exchange=EXCHANGE, symbol=SYMBOL)
SEED_MINUTES = 1500
"""A full ring buffer, so the sixty minutes replayed below make it slide."""

HOLE_AT = 20
"""Minute of the run whose candle never arrives over the websocket."""
BACKFILL_AT = 40
"""Minute of the run at which the hole is written *behind* the head -- the
``_push_candle_full_rewrite`` path of the market-worker, which is invisible to
anything that only reads the newest rows."""


class Buffer:
    """The candle list of one market, mutated the way the collector mutates it.

    Rows are packed once per candle and re-read afterwards, which is what Redis
    does: the bytes of a minute do not change until that minute is rewritten.
    """

    def __init__(self, redis: FakeHotState, *, maxlen: int = SEED_MINUTES) -> None:
        self.redis = redis
        self.maxlen = maxlen
        self.rows: list[tuple[datetime, bytes]] = []

    def _store(self) -> None:
        self.redis.lists[keys.candles_1m(EXCHANGE, SYMBOL)] = [row for _, row in self.rows]

    def push(self, item: NormalizedCandle) -> None:
        """LPUSH a new head (or LSET the head when the minute is the same)."""
        row = (item.open_time, candle_rows([item])[0])
        if self.rows and self.rows[0][0] == item.open_time:
            self.rows[0] = row
        else:
            self.rows.insert(0, row)
        del self.rows[self.maxlen :]
        self._store()

    def rewrite(self, item: NormalizedCandle) -> None:
        """A write older than the fast window: the whole list is rebuilt sorted."""
        self.rows = [entry for entry in self.rows if entry[0] != item.open_time]
        self.rows.append((item.open_time, candle_rows([item])[0]))
        self.rows.sort(key=lambda entry: entry[0], reverse=True)
        del self.rows[self.maxlen :]
        self._store()


def _scanner() -> Scanner:
    policy = build_policy()
    scanner = Scanner(
        config=ScannerConfig(exchange=EXCHANGE),
        policy=policy,
        registry=MarketRegistry(exchange=EXCHANGE),
        state=ScannerState(),
    )
    scanner.registry.apply([REF])
    scanner.cache = BaselineCache(gate=policy.gate)
    scanner.state.ensure(REF)
    return scanner


def _price(minute: int) -> Decimal:
    """A price that actually moves, so the features are not all constants."""
    return Decimal(100) + Decimal(minute % 17) / Decimal(10)


async def test_the_kept_context_and_the_rebuilt_one_produce_the_same_vector() -> None:
    redis = FakeHotState()
    buffer = Buffer(redis)
    for index in range(SEED_MINUTES):
        buffer.push(
            candle(
                ORIGIN + timedelta(minutes=index),
                close=_price(index),
                volume=Decimal(10) + Decimal(index % 7),
                symbol=SYMBOL,
            )
        )
    start = ORIGIN + timedelta(minutes=SEED_MINUTES)

    kept, rebuilt = _scanner(), _scanner()
    market_kept = kept.state.markets[SYMBOL]
    market_rebuilt = rebuilt.state.markets[SYMBOL]
    holed: NormalizedCandle | None = None
    compared = 0

    for minute in range(60):
        opened = start + timedelta(minutes=minute)
        closed = candle(
            opened, close=_price(minute), volume=Decimal(10) + Decimal(minute % 5), symbol=SYMBOL
        )
        forming = candle(
            opened,
            close=_price(minute) + Decimal("0.05"),
            is_final=False,
            event_ts=opened + timedelta(seconds=30),
            symbol=SYMBOL,
        )
        if minute == HOLE_AT:
            # The websocket never delivered this minute: nothing is pushed, and
            # the contiguous tail is broken for every window that spans it.
            holed = closed
        else:
            buffer.push(forming)
            for cut in (opened + timedelta(seconds=40), opened + timedelta(seconds=59)):
                if cut == opened + timedelta(seconds=59):
                    buffer.push(closed)
                if minute == BACKFILL_AT and holed is not None:
                    # The repaired minute lands behind the head, which is the
                    # only mutation a newest-rows-only reader cannot see.
                    buffer.rewrite(holed)
                    holed = None
                redis.strings[keys.book(EXCHANGE, SYMBOL)] = book_payload(ts=cut)
                redis.lists[keys.trades(EXCHANGE, SYMBOL)] = trade_rows(40, until=cut)
                redis.publish_coverage(session_since=ORIGIN, covered_until=cut)
                coverage = await read_coverage(cast("Any", redis), EXCHANGE, now=cut)
                kept.coverage = rebuilt.coverage = coverage

                batch = WriteBatch()
                # The rebuilt scanner throws its cache away before every cut,
                # which is what "decoded from the hot state, cold" means here.
                market_rebuilt.hot = HotCache()
                first = await kept.advance(cast("Any", redis), market_kept, batch, now=cut)
                second = await rebuilt.advance(cast("Any", redis), market_rebuilt, batch, now=cut)
                assert first is not None and second is not None
                assert first.vector.canonical_bytes() == second.vector.canonical_bytes(), (
                    f"vector differs at minute {minute}, cut {cut.isoformat()}"
                )
                assert canonical_json(first.features.state.as_wire()) == canonical_json(
                    second.features.state.as_wire()
                ), f"feature state differs at minute {minute}"
                compared += 1

    assert compared >= 60, "sixty minutes have to have been compared, not skipped"
    # The buffer is decoded once, cold; after that only the rows that changed --
    # here one forming update and one close per minute, plus the backfill. The
    # rebuilt scanner paid 1500 per cut for the same answer.
    assert market_kept.hot.candles.decoded < SEED_MINUTES + 150, (
        "a warm cache decodes the rows that arrived, not the buffer per cut"
    )
    assert market_rebuilt.hot.candles.decoded == SEED_MINUTES
    assert len(market_kept.hot.candles) == SEED_MINUTES


async def test_the_context_itself_is_equal_and_not_only_its_vector() -> None:
    """Compare the window, the forming candle and ``truncated`` -- not only the
    two outputs, because a divergence in data no feature reads today would be
    invisible in ``canonical_bytes()`` and would surface the day one does
    (Astra, T2.5c design review)."""
    redis = FakeHotState()
    buffer = Buffer(redis, maxlen=1500)
    for index in range(1499):
        buffer.push(candle(ORIGIN + timedelta(minutes=index), close=_price(index), symbol=SYMBOL))
    cache = HotCache()
    cut = ORIGIN + timedelta(minutes=1499, seconds=30)
    redis.publish_coverage(session_since=ORIGIN, covered_until=cut)
    coverage = await read_coverage(cast("Any", redis), EXCHANGE, now=cut)

    for pushed in (1499, 1500, 1501):
        while len(buffer.rows) < min(pushed, buffer.maxlen):
            index = len(buffer.rows) + max(0, pushed - buffer.maxlen)
            buffer.push(
                candle(ORIGIN + timedelta(minutes=index), close=_price(index), symbol=SYMBOL)
            )
        if pushed > 1500:
            buffer.push(
                candle(ORIGIN + timedelta(minutes=pushed - 1), close=_price(pushed), symbol=SYMBOL)
            )
        moment = ORIGIN + timedelta(minutes=pushed, seconds=10)
        redis.publish_coverage(session_since=ORIGIN, covered_until=moment)
        coverage = await read_coverage(cast("Any", redis), EXCHANGE, now=moment)
        warm = await build_market_context(
            cast("Any", redis),
            exchange=EXCHANGE,
            symbol=SYMBOL,
            coverage=coverage,
            cache=cache,
            now=moment,
        )
        cold = await build_market_context(
            cast("Any", redis),
            exchange=EXCHANGE,
            symbol=SYMBOL,
            coverage=coverage,
            cache=HotCache(),
            now=moment,
        )
        assert warm.context == cold.context, f"context differs with {pushed} minutes pushed"
        assert warm.context.candles_truncated == cold.context.candles_truncated
        assert len(warm.context.final_candles) == len(cold.context.final_candles)
