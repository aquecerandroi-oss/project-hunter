"""CPU-bound throughput: real OS processes vs one asyncio process (T3.74f).

**What T3.74f measured live (notes-T3.74f.md §1).** ``hunter-strategy-worker-1``
pinned at 97-100% of *one* core for the whole ~36-70s a 200-market burst took
to drain (docker stats, 2026-09-10 19:45Z and 20:00Z boundaries), while
``hunter-postgres-1`` stayed at 20-25% of its 12 cores the same window and
``pg_stat_activity`` showed most of its backends idle, waiting on the
*client* (this same Python process), not executing. A single ``asyncio``
process cannot spend more than one core's worth of CPU no matter how many
coroutines are "concurrent" -- the GIL serialises Python bytecode across
threads in one process, and ``BarDispatcher``'s concurrency (T3.74c/e) is
coroutines, not threads or processes.

**Why this benchmark is CPU-bound on purpose, unlike ``test_dispatch.py``'s
own ``TestThroughputAtTheMeasuredShape``** (``asyncio.sleep`` -- an I/O-bound
stand-in, where raising concurrency inside one process genuinely helps,
which is exactly what made T3.74e's projection plausible before this task
measured the real burst). The two are not interchangeable: this file proves
raising ``worker_concurrency`` further does nothing for a CPU-bound burst,
while splitting the same work across real OS processes (shards) does.
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor

import pytest

from hunter_strategy_worker.dispatch import BarDispatcher

pytestmark = pytest.mark.unit

MARKETS = 200
VERSIONS_PER_FAMILY = 11
TOTAL_EVALUATIONS = MARKETS * VERSIONS_PER_FAMILY  # 2200 -- T3.74's roster/universe shape
CPU_ITERATIONS = 8_000
"""Calibrated locally (not a guess) so one evaluation costs on the order of a
millisecond of real CPU -- small enough that 2200 of them (one full burst)
run in a few seconds on one core, large enough that process-pool startup
overhead does not dominate the comparison."""


def _cpu_bound_evaluation(n: int = CPU_ITERATIONS) -> int:
    """Stands in for one due-version's evaluation cost -- pure Python
    arithmetic in a tight loop (branches and modulo, the same *shape* of
    work ``Strategy.evaluate``'s ``Decimal`` math is: CPU, not I/O). Never
    ``asyncio.sleep``: that yields the event loop for free and would prove
    nothing about the GIL.
    """
    x = 0
    for i in range(n):
        x = (x * 1_000_003 + i) % 1_000_000_007
    return x


def _shard_worker(count: int) -> float:
    """One shard's whole share of the burst, run to completion in its own
    process. Module-level so :class:`ProcessPoolExecutor` can pickle and
    import it in the child."""
    started = time.perf_counter()
    for _ in range(count):
        _cpu_bound_evaluation()
    return time.perf_counter() - started


class TestRealProcessesBeatOneProcessOnCPUBoundWork:
    SHARDS = 4

    def test_four_shards_beat_one_process_by_bars_per_second(self) -> None:
        one_process_wall = _shard_worker(TOTAL_EVALUATIONS)

        per_shard = TOTAL_EVALUATIONS // self.SHARDS
        counts = [per_shard] * self.SHARDS
        # A production shard is a long-lived container, not spawned per
        # burst -- warm the pool (pay Windows/CI's `spawn` import cost once,
        # outside the timer) before measuring, so this compares steady-state
        # throughput, the number that actually matters for the report, not
        # process-startup latency.
        with ProcessPoolExecutor(max_workers=self.SHARDS) as pool:
            list(pool.map(_shard_worker, [0] * self.SHARDS))  # warm-up, zero work each
            started = time.perf_counter()
            list(pool.map(_shard_worker, counts))
            sharded_wall = time.perf_counter() - started

        bars_per_s_one = TOTAL_EVALUATIONS / one_process_wall
        bars_per_s_sharded = TOTAL_EVALUATIONS / sharded_wall
        speedup = one_process_wall / sharded_wall
        print(
            f"1 process: {one_process_wall:.2f}s ({bars_per_s_one:.0f} bars/s); "
            f"{self.SHARDS} shards: {sharded_wall:.2f}s ({bars_per_s_sharded:.0f} bars/s); "
            f"speedup={speedup:.2f}x"
        )
        # Not asserting the full 4x: an unevenly loaded CI/dev box makes that
        # noisy (measured locally, 22 cores available, across several runs:
        # 2.2x-3.8x). 1.8x is still well above what any amount of asyncio
        # concurrency alone gets on this same CPU-bound shape (the sibling
        # test below: ~1.0x) -- the point is that real cores, not more
        # coroutines, is what moves this number.
        assert speedup > 1.8, (
            f"expected real OS processes to beat one process substantially on "
            f"CPU-bound work; one_process={one_process_wall:.2f}s "
            f"sharded={sharded_wall:.2f}s speedup={speedup:.1f}x"
        )


class TestAsyncioConcurrencyAloneDoesNotHelpCPUBoundWork:
    """The other half of the finding: raising ``BarDispatcher``'s own
    concurrency (``ShadowConfig.worker_concurrency``, 8 -> 32 in T3.74e)
    helps an I/O-bound workload (``test_dispatch.py``'s own throughput test)
    but not a CPU-bound one -- more coroutines waiting their turn for the
    same one core, never more cores."""

    async def _dispatch_run(self, concurrency: int) -> float:
        dispatcher = BarDispatcher(concurrency=concurrency)
        started = time.perf_counter()
        for market_index in range(MARKETS):

            async def handler() -> None:
                for _ in range(VERSIONS_PER_FAMILY):
                    _cpu_bound_evaluation()

            await dispatcher.submit(f"market-{market_index}", f"msg-{market_index}", handler)
        await dispatcher.drain()
        return time.perf_counter() - started

    async def test_concurrency_32_barely_moves_a_cpu_bound_burst(self) -> None:
        serial = await self._dispatch_run(concurrency=1)
        concurrent_32 = await self._dispatch_run(concurrency=32)
        ratio = serial / concurrent_32
        print(
            f"concurrency=1: {serial:.2f}s; concurrency=32: {concurrent_32:.2f}s; ratio={ratio:.2f}"
        )
        # Generous band, not "no effect at all": some overlap is possible
        # while one coroutine holds the GIL and another is between bytecode
        # instructions, but nothing like the multi-x speedup an I/O-bound
        # workload gets from the same knob (test_dispatch.py's own test).
        assert 0.6 < ratio < 1.5, (
            f"expected asyncio concurrency to barely move a CPU-bound workload; "
            f"serial={serial:.2f}s concurrency_32={concurrent_32:.2f}s ratio={ratio:.2f}"
        )
