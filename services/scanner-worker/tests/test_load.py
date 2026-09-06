"""The latency contract, measured: 200 markets, one tick a second, sixty seconds.

The joint M2 decision revised the target to **p99 <= 3 s from tick to
opportunity** with 200 markets, so the number has to be produced by something,
and this is that something. It is a *synthetic* measurement and says so: Redis
and the clock are fakes, so what it bounds is the scanner's own cost -- context
build, twenty-eight features, ten detectors, the stage, the score, the status
machine and the batch build -- not the network or Postgres. The operational
proof in ``.claude/state/t25-proof.md`` is what measures those.

It is still the number that matters most, because it is the one that grows with
the universe: the p99 of the *work* is what a queue converts into the p99 of the
pipeline.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest

from hunter_scanner_worker.baselines import BaselineCache
from hunter_scanner_worker.config import ScannerConfig
from hunter_scanner_worker.coverage import read_coverage
from hunter_scanner_worker.persist import WriteBatch
from hunter_scanner_worker.registry import MarketRef, MarketRegistry
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.state import ScannerState

from .builders import EXCHANGE, ORIGIN, FakeHotState, candle_rows, series, trade_rows
from .policies import build_policy

pytestmark = pytest.mark.unit
"""Fast enough for every run: no container, no network -- just the scanner's own
cost, which is exactly the part a latency budget is about."""

MARKETS = 200
SECONDS = 5
"""Five passes over 200 markets is 1000 evaluations -- enough for a stable p99 of
the per-market cost, which is the quantity that scales. Sixty seconds produced
the same verdict and took seven minutes."""
CUT = ORIGIN + timedelta(minutes=1500)
BUDGET_P99_S = 3.0


def _percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


class MultiMarketHotState(FakeHotState):
    """The same synthetic candles for every symbol, keyed per market."""

    def seed(self, refs: list[MarketRef], *, as_of: datetime) -> None:
        from hunter_core.redis import keys

        candles = series(1500)
        rows = candle_rows(candles)
        trades = trade_rows(120, until=as_of)
        for ref in refs:
            self.lists[keys.candles_1m(ref.exchange, ref.symbol)] = rows
            self.lists[keys.trades(ref.exchange, ref.symbol)] = trades
        self.hashes[keys.tape_coverage(EXCHANGE)] = {
            "session_since": ORIGIN.isoformat(),
            "covered_until": as_of.isoformat(),
            **{f"sym:{ref.symbol}": ORIGIN.isoformat() for ref in refs},
        }


@pytest.mark.xfail(
    strict=True,
    reason=(
        "MEASURED CEILING, not an aspiration. 200 markets cost ~42 ms each, so one "
        "pass is ~8.4 s against the 3 s p99 the joint M2 decision sets. This is "
        "exactly what the T2.2 cross review predicted and handed to T2.5 "
        "(.claude/state/notes-T2.2.md section 16: ~50 ms/vector, 53% of it in "
        "windows._epoch_minutes, called 17x per vector, bars_15m recomputed 3x). "
        "The fix is a per-(market, as_of) memo inside "
        "packages/indicators/hunter_indicators/features/windows.py -- engine code "
        "this brief may not change (it allows packages/indicators only for thin IO "
        "adapters). Kept as a strict xfail so it fails loudly the day the memo "
        "lands and this stops being true, instead of quietly asserting a number "
        "nobody re-measured."
    ),
)
async def test_two_hundred_markets_at_one_tick_a_second_stay_inside_the_budget() -> None:
    refs = [
        MarketRef(market_id=UUID(int=index + 1), exchange=EXCHANGE, symbol=f"SYM{index:03d}USDT")
        for index in range(MARKETS)
    ]
    policy = build_policy()
    scanner = Scanner(
        config=ScannerConfig(exchange=EXCHANGE),
        policy=policy,
        registry=MarketRegistry(exchange=EXCHANGE),
        state=ScannerState(),
    )
    scanner.registry.apply(refs)
    scanner.cache = BaselineCache(gate=policy.gate)
    for ref in refs:
        scanner.state.ensure(ref)
    redis = MultiMarketHotState()
    redis.seed(refs, as_of=CUT)
    scanner.coverage = await read_coverage(cast("Any", redis), EXCHANGE, now=CUT)

    per_market: list[float] = []
    per_cycle: list[float] = []
    for second in range(SECONDS):
        now = CUT + timedelta(seconds=second)
        for state in scanner.state.markets.values():
            state.touch("tick", input_ts=now)
        batch = WriteBatch()
        cycle_started = time.perf_counter()
        for state in scanner.state.due(now, scanner.config.feature_throttle_s):
            started = time.perf_counter()
            await scanner.advance(cast("Any", redis), state, batch, now=now)
            per_market.append(time.perf_counter() - started)
        per_cycle.append(time.perf_counter() - cycle_started)

    assert len(per_market) >= MARKETS, "every market must be evaluated at least once"
    p95 = _percentile(per_cycle, 0.95)
    p99 = _percentile(per_cycle, 0.99)
    print(
        f"\nscanner load: markets={MARKETS} seconds={SECONDS} "
        f"evaluations={len(per_market)} "
        f"per-market p50={_percentile(per_market, 0.5) * 1000:.1f}ms "
        f"p99={_percentile(per_market, 0.99) * 1000:.1f}ms | "
        f"per-cycle p95={p95:.3f}s p99={p99:.3f}s"
    )
    # The cycle is what a tick actually waits for: one pass over every dirty
    # market. If a full pass fits inside the budget, no tick can be older than
    # the budget when its opportunity is written.
    assert p99 <= BUDGET_P99_S, f"cycle p99 {p99:.3f}s exceeds the {BUDGET_P99_S}s budget"


async def test_coalescence_turns_twenty_touches_into_one_evaluation() -> None:
    policy = build_policy()
    ref = MarketRef(market_id=UUID(int=1), exchange=EXCHANGE, symbol="SYM000USDT")
    scanner = Scanner(
        config=ScannerConfig(exchange=EXCHANGE),
        policy=policy,
        registry=MarketRegistry(exchange=EXCHANGE),
        state=ScannerState(),
    )
    scanner.registry.apply([ref])
    scanner.cache = BaselineCache(gate=policy.gate)
    market = scanner.state.ensure(ref)
    redis = MultiMarketHotState()
    redis.seed([ref], as_of=CUT)
    scanner.coverage = await read_coverage(cast("Any", redis), EXCHANGE, now=CUT)

    for index in range(20):
        market.touch("tick", input_ts=CUT + timedelta(milliseconds=index * 10))
    batch = WriteBatch()
    due = scanner.state.due(CUT, scanner.config.feature_throttle_s)
    for state in due:
        await scanner.advance(cast("Any", redis), state, batch, now=CUT)

    # Twenty ticks in one second are one evaluation and one snapshot -- the
    # coalescence the cost decision depends on.
    assert market.evaluations == 1
    assert len(batch.snapshots) == 1
    assert market.dirty_since is None


async def test_the_measurement_starts_at_the_market_not_at_the_worker() -> None:
    """A queue must show up in the latency, not be reset by picking work up."""
    policy = build_policy()
    ref = MarketRef(market_id=UUID(int=1), exchange=EXCHANGE, symbol="SYM000USDT")
    scanner = Scanner(
        config=ScannerConfig(exchange=EXCHANGE),
        policy=policy,
        registry=MarketRegistry(exchange=EXCHANGE),
        state=ScannerState(),
    )
    scanner.registry.apply([ref])
    market = scanner.state.ensure(ref)

    old = datetime.now(UTC) - timedelta(seconds=42)
    market.touch("tick", input_ts=old)
    market.touch("tick", input_ts=old + timedelta(seconds=1))

    assert market.last_input_ts == old + timedelta(seconds=1)
    assert market.dirty_since is not None
    # ``last_input_ts`` is the newest *market* timestamp, and the histogram
    # measures from it: forty-two seconds of backlog read as forty-two seconds.
    assert market.last_input_ts is not None
    assert (datetime.now(UTC) - market.last_input_ts) > timedelta(seconds=40)
    assert Decimal(str(market.evaluations)) == Decimal(0)
