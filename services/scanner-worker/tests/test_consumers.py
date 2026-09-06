"""Batch consumption and coalescence of the notification streams (T2.5d).

The number that forced this: in the T2.5c window the ``market.ticks`` consumer
handled ~71 messages/s against 151 produced and stayed ~95 000 behind, i.e. about
ten minutes late, permanently — on a stream whose entire handling is one dict
touch (``.claude/state/t25-proof.md``, T2.5c §3). The cost was the round trips
around each message, so the fix is to read, coalesce and complete a whole batch.

**Coalescence is sound here and only here.** A tick is a notification: the
evidence is the hot state, read at the current cut, so twenty ticks of one market
in one batch are one evaluation and the nineteen absorbed ones cost nothing.
``market.candles.closed`` keeps the per-message consumer with its deferred ACK,
because a closed candle *is* a durable effect.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.streams import Streams
from hunter_scanner_worker import consumers as consumers_mod
from hunter_scanner_worker.config import ScannerConfig
from hunter_scanner_worker.consumers import ConsumerHealth, coalesce, run_batch_consumer
from hunter_scanner_worker.registry import MarketRegistry
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.state import ScannerState

from .builders import EXCHANGE, REF, SYMBOL
from .policies import build_policy

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _tick(symbol: str, ts: datetime) -> EventEnvelope:
    return EventEnvelope(
        type=Streams.MARKET_TICKS,
        producer="market-worker@test",
        key=f"{EXCHANGE}:{symbol}",
        payload={"symbol": symbol, "ts": ts.isoformat()},
    )


def _batch(*envelopes: EventEnvelope) -> list[tuple[str, EventEnvelope]]:
    return [(f"1-{index}", envelope) for index, envelope in enumerate(envelopes, start=1)]


class _Runtime:
    def __init__(self) -> None:
        self.instance = "test:1"
        self.errors = 0
        self.successes = 0

    def mark_error(self) -> None:
        self.errors += 1

    def mark_success(self) -> None:
        self.successes += 1


class TestCoalescence:
    def test_many_ticks_of_one_market_become_one_touch_with_the_newest_stamp(self) -> None:
        """The scanner reads the hot state at the current cut, so the newest
        stamp is the one that describes the evidence it will actually see."""
        stamps = [NOW - timedelta(seconds=offset) for offset in (30, 10, 20)]
        result = coalesce(_batch(*[_tick(SYMBOL, stamp) for stamp in stamps]))

        assert result.newest == {SYMBOL: NOW - timedelta(seconds=10)}
        assert result.absorbed == 2

    def test_two_markets_in_one_batch_are_two_touches_and_nothing_absorbed(self) -> None:
        result = coalesce(_batch(_tick("BTCUSDT", NOW), _tick("ETHUSDT", NOW)))

        assert set(result.newest) == {"BTCUSDT", "ETHUSDT"}
        assert result.absorbed == 0

    def test_a_message_with_no_market_is_not_counted_as_absorbed(self) -> None:
        """Absorbed means "a notification another one already covers". A message
        nobody can attribute to a market covers nothing and must not inflate the
        counter (Astra, T2.5d design review)."""
        orphan = EventEnvelope(type=Streams.MARKET_TICKS, producer="p", key="", payload={})

        result = coalesce(_batch(orphan, _tick(SYMBOL, NOW)))

        assert result.newest == {SYMBOL: NOW}
        assert result.absorbed == 0

    def test_the_oldest_stamp_of_the_batch_is_reported_before_coalescence_hides_it(self) -> None:
        """The maximum is what the evaluation uses and the minimum is what the
        queue costs; keeping only the first would make a ten-minute backlog
        invisible in the numbers (Astra, T2.5d design review, must-fix 4)."""
        old = NOW - timedelta(minutes=10)
        result = coalesce(_batch(_tick(SYMBOL, old), _tick(SYMBOL, NOW)))

        assert result.oldest == old
        assert result.newest == {SYMBOL: NOW}

    def test_an_empty_batch_says_nothing_instead_of_guessing(self) -> None:
        result = coalesce([])

        assert result.newest == {} and result.absorbed == 0 and result.oldest is None


class TestBatchConsumer:
    async def test_every_message_of_the_batch_is_acked_not_only_the_survivor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Twenty absorbed ticks are twenty finished messages. Acking only the
        one that produced the touch would leave nineteen pending for
        ``XAUTOCLAIM`` to bring back forever (Astra, T2.5d, must-fix 3)."""
        delivered = _batch(*[_tick(SYMBOL, NOW) for _ in range(20)])
        acked: list[list[tuple[str, EventEnvelope]]] = []
        handled: list[int] = []

        await self._run_once(monkeypatch, delivered, acked, handled)

        assert handled == [20]
        assert [message_id for message_id, _envelope in acked[0]] == [
            message_id for message_id, _envelope in delivered
        ]

    async def test_a_handler_that_raises_leaves_the_whole_batch_pending(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Not everything completed, so nothing may be marked processed: the
        batch comes back through the pending list instead of being lost. Redoing
        the touches the handler had already applied is free and exact (a set of
        reasons and a maximum stamp), which is what makes replaying the whole
        batch the right unit (Astra, T2.5d diff review)."""
        delivered = _batch(_tick(SYMBOL, NOW))
        acked: list[list[tuple[str, EventEnvelope]]] = []
        runtime = _Runtime()

        async def explode(_deliveries: list[tuple[str, EventEnvelope]]) -> None:
            raise RuntimeError("handler is broken")

        await self._drive(monkeypatch, delivered, acked, explode, runtime)

        assert acked == []
        assert runtime.errors == 1

    async def test_an_empty_batch_keeps_the_consumer_alive_without_acking(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Everything in the read was already processed. That is a healthy
        iteration, not a message and not an error."""
        acked: list[list[tuple[str, EventEnvelope]]] = []
        handled: list[int] = []
        health = await self._run_once(monkeypatch, [], acked, handled)

        assert handled == [] and acked == []
        assert health.last_iteration_at.get(Streams.MARKET_TICKS) is not None
        assert health.last_message_at.get(Streams.MARKET_TICKS) is None

    async def _run_once(
        self,
        monkeypatch: pytest.MonkeyPatch,
        delivered: list[tuple[str, EventEnvelope]],
        acked: list[list[tuple[str, EventEnvelope]]],
        handled: list[int],
    ) -> ConsumerHealth:
        async def handle(deliveries: list[tuple[str, EventEnvelope]]) -> None:
            handled.append(len(deliveries))

        return await self._drive(monkeypatch, delivered, acked, handle, _Runtime())

    async def _drive(
        self,
        monkeypatch: pytest.MonkeyPatch,
        delivered: list[tuple[str, EventEnvelope]],
        acked: list[list[tuple[str, EventEnvelope]]],
        handle: Any,
        runtime: _Runtime,
    ) -> ConsumerHealth:
        async def one_batch(
            *_args: Any, **_kwargs: Any
        ) -> AsyncIterator[list[tuple[str, EventEnvelope]]]:
            yield delivered
            raise asyncio.CancelledError

        async def record_ack(
            _redis: Any, _stream: str, _group: str, items: list[tuple[str, EventEnvelope]]
        ) -> None:
            acked.append(list(items))

        monkeypatch.setattr(consumers_mod, "consume_batches", one_batch)
        monkeypatch.setattr(consumers_mod, "ack_many", record_ack)
        health = ConsumerHealth()
        with pytest.raises(asyncio.CancelledError):
            await run_batch_consumer(
                None,  # type: ignore[arg-type]
                runtime,  # type: ignore[arg-type]
                Streams.MARKET_TICKS,
                health,
                handle,
                block_ms=2000,
                batch=500,
            )
        return health


class TestTouchHandler:
    def _scanner(self) -> Scanner:
        scanner = Scanner(
            config=ScannerConfig(exchange=EXCHANGE),
            policy=build_policy(),
            registry=MarketRegistry(exchange=EXCHANGE),
            state=ScannerState(),
        )
        scanner.registry.apply([REF])
        scanner.state.ensure(REF, now=NOW - timedelta(hours=1))
        return scanner

    async def test_the_batch_handler_marks_the_market_once_with_the_newest_input(self) -> None:
        from hunter_scanner_worker.main import touch_batch_handler

        scanner = self._scanner()
        handle = touch_batch_handler(scanner, Streams.MARKET_TICKS)
        older, newer = NOW - timedelta(seconds=5), NOW

        await handle(_batch(_tick(SYMBOL, older), _tick(SYMBOL, newer)))

        state = scanner.state.markets[SYMBOL]
        assert state.last_input_ts == newer
        assert state.dirty_reasons == {Streams.MARKET_TICKS}

    async def test_the_absorbed_notifications_are_counted(self) -> None:
        from hunter_core.observability import registry
        from hunter_scanner_worker.main import touch_batch_handler

        scanner = self._scanner()
        handle = touch_batch_handler(scanner, Streams.MARKET_TICKS)

        def absorbed() -> float:
            value = registry.get_sample_value(
                "hunter_scanner_ticks_coalesced_total", {"stream": Streams.MARKET_TICKS}
            )
            return 0.0 if value is None else value

        before = absorbed()
        await handle(_batch(*[_tick(SYMBOL, NOW) for _ in range(5)]))

        assert absorbed() - before == 4
