"""``BarDispatcher``/``market_key`` — no database, no Redis (T3.74c).

Three properties this module exists to guarantee, each its own test class:

1. **Bounded concurrency.** No more than ``concurrency`` handlers run at once.
2. **Per-market ordering.** Two bars of the *same* market never run
   concurrently and always run in the order they were submitted, even while
   other markets run in parallel.
3. **Throughput at the measured shape.** A synthetic 11 versions x 200
   markets workload (T3.74's roster/universe, ``notes-T3.74.md`` §2c) --
   handlers with a fixed simulated cost, standing in for one real
   ``handle_candle`` call, so the comparison is about the *dispatcher*, not
   about Postgres. The DB-backed proof that real decisions survive
   concurrency unchanged is ``test_dispatch_benchmark.py`` (a testcontainer,
   at a tractable market count -- 2200 real evaluations at T3.74b's measured
   ~1.4/s would take the better part of half an hour, which is not a test).
"""

from __future__ import annotations

import asyncio
import time

import pytest

from hunter_core.observability import registry
from hunter_strategy_worker.dispatch import BarDispatcher, market_key

pytestmark = pytest.mark.unit


def _skipped(reason: str) -> float:
    value = registry.get_sample_value("hunter_shadow_bars_skipped_total", {"reason": reason})
    return 0.0 if value is None else value


class TestMarketKey:
    def test_two_payloads_of_the_same_market_share_a_key(self) -> None:
        a = {"exchange": "binance", "symbol": "BTCUSDT", "market_type": "perpetual", "close": "1"}
        b = {"exchange": "binance", "symbol": "BTCUSDT", "market_type": "perpetual", "close": "2"}
        assert market_key(a) == market_key(b)

    def test_a_different_symbol_or_market_type_is_a_different_key(self) -> None:
        base = {"exchange": "binance", "symbol": "BTCUSDT", "market_type": "perpetual"}
        other_symbol = {**base, "symbol": "ETHUSDT"}
        other_type = {**base, "market_type": "spot"}
        assert market_key(base) != market_key(other_symbol)
        assert market_key(base) != market_key(other_type)

    def test_a_missing_field_never_raises(self) -> None:
        assert market_key({}) == "?:?:?"


class TestBoundedConcurrency:
    async def test_no_more_than_concurrency_handlers_run_at_once(self) -> None:
        dispatcher = BarDispatcher(concurrency=3)
        in_flight = 0
        peak = 0

        async def handler() -> None:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.02)
            in_flight -= 1

        for i in range(12):
            await dispatcher.submit(f"market-{i}", f"msg-{i}", handler)
        await dispatcher.drain()

        assert peak == 3, "the semaphore let more than `concurrency` handlers run at once"

    async def test_a_full_dispatcher_applies_backpressure_on_submit(self) -> None:
        """``submit`` itself blocks once every slot is taken -- the reader
        (``run_consumer``'s ``async for``) is throttled, not a queue growing
        without bound behind it."""
        dispatcher = BarDispatcher(concurrency=1)
        release = asyncio.Event()

        async def blocking_handler() -> None:
            await release.wait()

        await dispatcher.submit("m1", "msg-1", blocking_handler)  # takes the only slot

        submitted_second = False

        async def mark_and_submit() -> None:
            nonlocal submitted_second
            await dispatcher.submit("m2", "msg-2", lambda: asyncio.sleep(0))
            submitted_second = True

        task = asyncio.ensure_future(mark_and_submit())
        await asyncio.sleep(0.01)
        assert submitted_second is False, "submit() returned before a slot was free"
        release.set()
        await task
        assert submitted_second is True
        await dispatcher.drain()


class TestPerMarketOrdering:
    async def test_two_bars_of_the_same_market_never_run_concurrently(self) -> None:
        dispatcher = BarDispatcher(concurrency=8)
        overlapping = False
        active: set[int] = set()

        async def handler(bar: int) -> None:
            nonlocal overlapping
            if active:
                overlapping = True
            active.add(bar)
            await asyncio.sleep(0.02)
            active.discard(bar)

        for bar in range(5):
            await dispatcher.submit("same-market", f"bar-{bar}", lambda b=bar: handler(b))
        await dispatcher.drain()

        assert overlapping is False

    async def test_two_bars_of_the_same_market_run_in_submission_order(self) -> None:
        dispatcher = BarDispatcher(concurrency=8)
        order: list[int] = []

        async def handler(bar: int) -> None:
            await asyncio.sleep(0.01 * (3 - bar) if bar < 3 else 0)  # later bars finish "faster"
            order.append(bar)

        for bar in range(4):
            await dispatcher.submit("same-market", f"bar-{bar}", lambda b=bar: handler(b))
        await dispatcher.drain()

        assert order == [0, 1, 2, 3], "a later bar of the same market ran before an earlier one"

    async def test_different_markets_do_run_concurrently(self) -> None:
        """The point of all this: markets that never shared a slot row must
        not be serialised behind one another."""
        dispatcher = BarDispatcher(concurrency=8)
        started = asyncio.Event()
        both_ran = asyncio.Event()
        seen: set[str] = set()

        async def handler(key: str) -> None:
            seen.add(key)
            if len(seen) == 2:
                both_ran.set()
            else:
                await started.wait()
            started.set()

        for key in ("market-a", "market-b"):
            await dispatcher.submit(key, f"msg-{key}", lambda k=key: handler(k))
        await asyncio.wait_for(both_ran.wait(), timeout=1.0)
        await dispatcher.drain()
        assert seen == {"market-a", "market-b"}


class TestCancelAll:
    async def test_cancel_all_stops_in_flight_handlers(self) -> None:
        dispatcher = BarDispatcher(concurrency=2)
        cancelled = False

        async def handler() -> None:
            nonlocal cancelled
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled = True
                raise

        await dispatcher.submit("m1", "msg-1", handler)
        await asyncio.sleep(0.01)
        await dispatcher.cancel_all()
        assert cancelled is True


class TestThroughputAtTheMeasuredShape:
    """11 versions x 200 markets (T3.74's roster/universe), handlers with a
    fixed simulated cost standing in for one real ``handle_candle`` call."""

    MARKETS = 200
    VERSIONS_PER_FAMILY = 11
    SIMULATED_BAR_COST_S = 0.01
    CONCURRENCY = 8

    async def _run(self, concurrency: int) -> float:
        dispatcher = BarDispatcher(concurrency=concurrency)
        started = time.perf_counter()
        for market_index in range(self.MARKETS):
            key = f"market-{market_index}"

            async def handler() -> None:
                # Standing in for one handle_candle call across its due
                # versions -- the dispatcher does not know or care what is
                # inside, only that it is one unit of work for one market.
                await asyncio.sleep(self.SIMULATED_BAR_COST_S)

            await dispatcher.submit(key, f"msg-{market_index}", handler)
        await dispatcher.drain()
        return time.perf_counter() - started

    async def test_concurrency_cuts_wall_time_by_roughly_the_concurrency_factor(self) -> None:
        serial = await self._run(concurrency=1)
        concurrent = await self._run(concurrency=self.CONCURRENCY)
        speedup = serial / concurrent
        # Not asserting the full 8x: asyncio scheduling overhead at 200
        # markets makes that noisy on a loaded CI box. Half of it is already
        # far more than the ~10% T3.74b's cache-only change measured, and
        # is the number that matters for the report.
        assert speedup > self.CONCURRENCY / 2, (
            f"expected concurrency to help substantially; serial={serial:.2f}s "
            f"concurrent={concurrent:.2f}s speedup={speedup:.1f}x"
        )


class TestDuplicateMessageIsRefused:
    """T3.74d code review, HIGH: a stream redelivery (``consume()``'s
    ``XAUTOCLAIM`` reclaiming a message this same consumer still holds,
    because it sat queued longer than ``claim_idle_ms``) must not run the
    handler a second time -- neither while the first submission is still
    *queued* behind a full dispatcher, nor while it is already *running*.
    """

    async def test_a_message_id_already_running_is_refused_not_run_twice(self) -> None:
        dispatcher = BarDispatcher(concurrency=1)
        release = asyncio.Event()
        runs: list[str] = []

        async def blocking_handler() -> None:
            runs.append("first")
            await release.wait()

        await dispatcher.submit("market-a", "msg-1", blocking_handler)
        await asyncio.sleep(0)  # let the background task actually start running

        async def second_handler() -> None:
            runs.append("second")

        before = _skipped("already_in_flight")
        await dispatcher.submit("market-a", "msg-1", second_handler)  # the redelivery
        assert _skipped("already_in_flight") == before + 1
        assert runs == ["first"], "the redelivered duplicate must not run its own handler"

        release.set()
        await dispatcher.drain()
        assert runs == ["first"]

    async def test_a_message_id_only_queued_not_yet_running_is_also_refused(self) -> None:
        """The guard is recorded *before* the semaphore wait -- a redelivery
        of a bar still waiting for a concurrency slot (never mind whether its
        handler has started) must be refused too."""
        dispatcher = BarDispatcher(concurrency=1)
        release = asyncio.Event()

        async def blocking_handler() -> None:
            await release.wait()

        await dispatcher.submit("market-a", "msg-1", blocking_handler)  # takes the only slot

        queued_ran = False

        async def queued_handler() -> None:
            nonlocal queued_ran
            queued_ran = True

        before = _skipped("already_in_flight")
        # Same message id, a different key -- the guard is keyed on the
        # message id alone, exactly what a stream redelivery repeats.
        await dispatcher.submit("market-b", "msg-1", queued_handler)
        assert _skipped("already_in_flight") == before + 1

        release.set()
        await dispatcher.drain()
        assert queued_ran is False, "the duplicate must never run, even after the slot frees"

    async def test_after_completion_the_same_message_id_may_run_again(self) -> None:
        """Not a permanent block -- once a message is fully handled (finally
        clause), its id is free again, the same as a genuinely new delivery of
        the same stream id would need to be (e.g. a replay)."""
        dispatcher = BarDispatcher(concurrency=1)
        runs: list[str] = []

        async def handler() -> None:
            runs.append("ran")

        await dispatcher.submit("market-a", "msg-1", handler)
        await dispatcher.drain()
        await dispatcher.submit("market-a", "msg-1", handler)
        await dispatcher.drain()
        assert runs == ["ran", "ran"]
