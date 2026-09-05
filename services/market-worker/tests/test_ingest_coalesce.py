"""Pure tick-coalescing logic — no IO, so this runs without Docker.

docs/plans/M1.md T1.3 verification: "10 trades in 100 ms -> 1 market.ticks event".
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_market_worker.ingest import AcceptedEvents, TickCoalescer, build_tick_payload

from . import builders

pytestmark = pytest.mark.unit


def test_ten_trades_coalesce_into_one_dirty_entry() -> None:
    coalescer = TickCoalescer()
    for i in range(10):
        coalescer.on_trade(builders.trade("BTCUSDT", "100", "0.5", trade_id=str(i)))

    dirty = coalescer.dirty_items()
    assert len(dirty) == 1
    (exchange, symbol), accum = dirty[0]
    assert (exchange, symbol) == (builders.EXCHANGE, "BTCUSDT")
    assert accum.trades_count == 10
    assert accum.volume_delta == Decimal("5")


def test_reset_clears_counters_but_keeps_last_price() -> None:
    coalescer = TickCoalescer()
    coalescer.on_trade(builders.trade("BTCUSDT", "100", "1"))
    key = (builders.EXCHANGE, "BTCUSDT")
    coalescer.reset(key)

    assert coalescer.dirty_items() == []
    accum = coalescer._state[key]  # pyright: ignore[reportPrivateUsage]  # white-box assertion on purpose
    assert accum.trades_count == 0
    assert accum.volume_delta == Decimal(0)
    assert accum.price == Decimal("100")  # last price survives a reset


def test_ticker_and_book_update_the_same_accumulator() -> None:
    coalescer = TickCoalescer()
    coalescer.on_ticker(builders.ticker("BTCUSDT", "50000"))
    coalescer.on_book(builders.order_book("BTCUSDT", best_bid="49999", best_ask="50001"))

    [(_, accum)] = coalescer.dirty_items()
    assert accum.price == Decimal("50000")
    assert accum.book_imbalance_5 is not None


def test_build_tick_payload_shape() -> None:
    coalescer = TickCoalescer()
    trade_ts = builders.utcnow()
    coalescer.on_trade(builders.trade("BTCUSDT", "100", "2", ts=trade_ts))
    [(_, accum)] = coalescer.dirty_items()

    payload = build_tick_payload("fake", "BTCUSDT", accum, "2026-01-01T00:00:00+00:00")

    assert payload == {
        "exchange": "fake",
        "symbol": "BTCUSDT",
        "price": "100",
        "bid": None,
        "ask": None,
        "volume_delta": "2",
        "trades_count": 1,
        "book_imbalance_5": None,
        "ts": "2026-01-01T00:00:00+00:00",
        "price_ts": trade_ts.isoformat(),
        "book_ts": None,
    }


def test_book_only_update_does_not_refresh_price_ts() -> None:
    """H10: a book-only update must not republish a frozen price under a
    fresh timestamp — ``ts`` advances but ``price_ts`` stays at the last
    price-bearing event; ``book_ts`` tracks the book separately."""
    coalescer = TickCoalescer()
    t0 = builders.utcnow()
    t1 = t0 + timedelta(seconds=5)
    coalescer.on_ticker(builders.ticker("BTCUSDT", "100", ts=t0))
    book_at_t1 = builders.order_book("BTCUSDT").model_copy(update={"ts": t1})
    coalescer.on_book(book_at_t1)

    [(_, accum)] = coalescer.dirty_items()
    assert accum.ts is not None
    payload = build_tick_payload("fake", "BTCUSDT", accum, accum.ts.isoformat())

    assert payload["ts"] == t1.isoformat()
    assert payload["price_ts"] == t0.isoformat()
    assert payload["book_ts"] == t1.isoformat()


def test_ts_tracking_matches_old_string_based_max_for_shuffled_events() -> None:
    """B5: ``_TickAccum`` now stores ``datetime`` objects and formats to ISO
    only at flush time — the old code ran ``datetime.fromisoformat`` twice
    per event just to ``max()`` over ISO strings (ingest.py:92-93,102-103,
    110-111 per t16b profile). Same shuffled event sequence, same output."""
    import random

    rand = random.Random(20260905)
    base = builders.utcnow()
    events: list[tuple[str, Any]] = []
    for i in range(30):
        offset = timedelta(milliseconds=rand.randint(-500, 500) + i * 10)
        ts = base + offset
        kind = rand.choice(["ticker", "trade", "book"])
        if kind == "ticker":
            events.append(("ticker", builders.ticker("BTCUSDT", "100", ts=ts)))
        elif kind == "trade":
            events.append(("trade", builders.trade("BTCUSDT", "100", "1", ts=ts)))
        else:
            events.append(("book", builders.order_book("BTCUSDT").model_copy(update={"ts": ts})))

    # Old algorithm: track/compare ISO *strings* via datetime.fromisoformat.
    old_ts = old_price_ts = old_book_ts = ""

    def old_max(current: str, candidate: str) -> str:
        return max(filter(None, [current, candidate]), key=datetime.fromisoformat)

    for kind, event in events:
        event_ts: str = event.ts.isoformat()
        old_ts = old_max(old_ts, event_ts)
        if kind in ("ticker", "trade"):
            old_price_ts = old_max(old_price_ts, event_ts)
        if kind == "book":
            old_book_ts = old_max(old_book_ts, event_ts)

    coalescer = TickCoalescer()
    for kind, event in events:
        if kind == "ticker":
            coalescer.on_ticker(event)  # pyright: ignore[reportArgumentType]
        elif kind == "trade":
            coalescer.on_trade(event)  # pyright: ignore[reportArgumentType]
        else:
            coalescer.on_book(event)  # pyright: ignore[reportArgumentType]

    [(_, accum)] = coalescer.dirty_items()
    new_ts = accum.ts.isoformat() if accum.ts else ""
    payload = build_tick_payload("fake", "BTCUSDT", accum, new_ts)

    assert new_ts == old_ts
    assert payload["price_ts"] == (old_price_ts or None)
    assert payload["book_ts"] == (old_book_ts or None)


def test_duplicate_component_is_rejected_after_first_acceptance() -> None:
    accepted = AcceptedEvents()
    event = builders.ticker("BTCUSDT", "100")
    assert accepted.accept(event)
    assert not accepted.accept(event)


def test_enqueue_has_no_dead_queuefull_handler() -> None:
    """L1: BoundedEvents.put_nowait never raises QueueFull (it drops with a
    metric internally) — the except clause was dead code."""
    import inspect

    from hunter_market_worker import ingest

    source = inspect.getsource(ingest)
    assert "except asyncio.QueueFull" not in source
