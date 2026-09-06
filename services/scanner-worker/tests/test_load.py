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
SECONDS = 6
"""Six passes over 200 markets is 1200 evaluations -- enough for a stable p99 of
the per-market cost, which is the quantity that scales. Sixty seconds produced
the same verdict and took seven minutes."""
CUT = ORIGIN + timedelta(minutes=1500)
BUDGET_P99_S = 3.0
WARMUP_CEILING_S = 20.0
"""The **first** pass decodes 1500 rows for all 200 markets, because no market
has a cache yet: 13.3 s measured here. It is reported apart from the budget on
purpose -- the p99 the joint decision asks for is of *healthy operation*, and a
process that has not yet read a market has no tick to be late for. What a
restart costs is the operational proof's business (``.claude/state/t25-proof.md``),
and this ceiling only keeps the warm-up from silently doubling."""


def _percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


class MultiMarketHotState(FakeHotState):
    """The same synthetic *shape* for every symbol, seeded under its own key.

    Each market's rows carry that market's own symbol: ``build_context`` drops
    candles belonging to another market, so seeding BTCUSDT's rows under every
    key -- what this fixture did until T2.5c -- made the engine measure an empty
    context and the number meant nothing (notes-T2.2 section 18).
    """

    def seed(self, refs: list[MarketRef], *, as_of: datetime) -> None:
        from hunter_core.redis import keys

        # A **full** tape, not a token one: ``TRADES_MAXLEN`` is 2000 and the
        # busy markets do fill it, so a 120-trade fixture measured a tenth of
        # the decode the container pays (notes-T2.5 section 25).
        trades = trade_rows(2000, until=as_of)
        for ref in refs:
            rows = candle_rows(series(1500, symbol=ref.symbol))
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
        "MEASURED, and 8% out: cycle p99 3.23 s against the 3.0 s budget, with "
        "every one of the 200 markets holding a FULL hot state (1500 candle rows "
        "and a maxed-out 2000-trade tape). That worst case is what a mature "
        "deployment looks like -- the tape ring buffer was full for 75% of the "
        "real universe when this was measured (notes-T2.5 section 25) -- so the "
        "fixture is not pessimistic on purpose. T2.5c took the per-market cost "
        "from 66.6 ms to 13.4 ms (decode reuse by row + the derived windows "
        "carried between ticks); what is left is 200 x 13.4 ms, and its two "
        "biggest parts are OUTSIDE this service: "
        "hunter_indicators.features.context.build_context re-scans and re-sorts "
        "the 1500 candles and MarketContext.__post_init__ re-validates them and "
        "the 2000 trades on every tick (~3.1 ms profiled per market between "
        "them), for a cut that moved by one second. The remedy is a construction "
        "path for a context whose sources were already checked -- packages/**, "
        "and this brief may not touch it. The operational number is in "
        "``.claude/state/t25-proof.md`` (T2.5c): against the real stack, where "
        "candle buffers are ~790 rows and the loop also serves the consumers, "
        "the p99 of the histogram is what decides acceptance. Kept as a strict "
        "xfail so the day that construction path lands, this fails by passing. "
        "T2.5d did NOT change this number and could not: the fixture is a fake "
        "Redis, so neither the batched consumption nor hiredis touches it (both "
        "pay off in transport, and this test has none). What T2.5d changed is "
        "the operational side -- market.ticks lag 0, scanner CPU 97-145% -> 55%, "
        "hot-state read 23.8-32.9 ms -> 3.3-4.3 ms per market -- and the "
        "operational p99 is still out of budget for a reason that is now "
        "upstream: a tick is already ~3.7 s old (median) when the collector "
        "XADDs it (``.claude/state/t25-proof.md``, T2.5d section 5)."
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
    warmup, steady = per_cycle[0], per_cycle[1:]
    warm_markets = per_market[MARKETS:]
    p95 = _percentile(steady, 0.95)
    p99 = _percentile(steady, 0.99)
    decoded = sum(state.hot.candles.decoded for state in scanner.state.markets.values())
    print(
        f"\nscanner load: markets={MARKETS} seconds={SECONDS} "
        f"evaluations={len(per_market)} "
        f"per-market p50={_percentile(warm_markets, 0.5) * 1000:.1f}ms "
        f"p99={_percentile(warm_markets, 0.99) * 1000:.1f}ms | "
        f"per-cycle p95={p95:.3f}s p99={p99:.3f}s | "
        f"warm-up pass {warmup:.3f}s | rows decoded {decoded}"
    )
    # The cycle is what a tick actually waits for: one pass over every dirty
    # market. If a full pass fits inside the budget, no tick can be older than
    # the budget when its opportunity is written.
    assert p99 <= BUDGET_P99_S, f"cycle p99 {p99:.3f}s exceeds the {BUDGET_P99_S}s budget"
    assert warmup <= WARMUP_CEILING_S, f"the cold pass took {warmup:.3f}s"
    # 1500 rows once per market and nothing after: the fixture never rewrites a
    # row, and re-decoding unchanged rows is exactly the cost T2.5c removed.
    assert decoded == MARKETS * 1500, decoded


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


def _samples(histogram: Any) -> float:
    for metric in histogram.collect():
        for sample in metric.samples:
            if sample.name.endswith("_count"):
                return float(sample.value)
    raise AssertionError("the histogram must expose a _count sample")


async def test_the_latency_sample_is_taken_after_the_projections_are_published() -> None:
    """The budget is "tick to **opportunity**", so the publish is inside it.

    Until T2.5c the histogram was observed inside ``Scanner.advance``, which left
    ``features.updated`` and the Radar projection outside the number that is
    supposed to bound them (Astra, T2.5c design review). Two facts are asserted
    here: ``advance`` alone samples nothing, and by the time the loop publishes
    the Radar row the sample has *not* been taken yet.
    """
    import asyncio

    from pydantic import SecretStr

    from hunter_core.runtime import WorkerRuntime
    from hunter_core.settings import Settings
    from hunter_scanner_worker import publish as projections
    from hunter_scanner_worker.health import CycleHealth
    from hunter_scanner_worker.metrics import scanner_tick_to_opportunity_seconds
    from hunter_scanner_worker.runners import evaluation_loop

    ref = MarketRef(market_id=UUID(int=1), exchange=EXCHANGE, symbol="SYM000USDT")
    policy = build_policy()
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
    market.touch("tick", input_ts=CUT)

    at_publish: list[float] = []
    original = projections.publish_features

    async def spy(*args: Any, **kwargs: Any) -> None:
        at_publish.append(_samples(scanner_tick_to_opportunity_seconds))
        await original(*args, **kwargs)

    # ``publish_features`` rather than ``publish_radar``: it goes out on every
    # evaluation, while the Radar row needs a score, and with an empty baseline
    # archive there is none (T2.4: degraded is not evidence).
    projections.publish_features = spy  # type: ignore[assignment]
    settings = Settings(
        database_url=SecretStr("postgresql+asyncpg://u:p@localhost/x"),
        redis_url=SecretStr("redis://localhost:6379/0"),
    )
    runtime = WorkerRuntime(
        "scanner", settings, engine=cast("Any", None), redis_client=cast("Any", redis)
    )
    before = _samples(scanner_tick_to_opportunity_seconds)
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(
                evaluation_loop(
                    scanner, cast("Any", None), cast("Any", redis), runtime, CycleHealth()
                ),
                0.6,
            )
    finally:
        projections.publish_features = original  # type: ignore[assignment]

    assert market.evaluations >= 1, "the loop has to have evaluated the market"
    after = _samples(scanner_tick_to_opportunity_seconds)
    assert after > before, "the loop has to have sampled the latency"
    assert at_publish, "the loop has to have published the vector"
    assert at_publish[0] == before, "no sample had been taken when the vector went out"


async def test_a_radar_row_redis_refused_is_not_counted_as_delivered() -> None:
    """A latency sample claims a delivery, so a failed write must not produce one.

    ``publish_radar`` swallows the Redis error on purpose (the projection is
    ephemeral and the durable row is already committed), which is exactly why
    the histogram may not treat "we tried" as "it is on the Radar" (Astra,
    T2.5c diff review, must-fix 2).
    """
    from hunter_scanner_worker import publish as projections
    from hunter_scanner_worker.metrics import scanner_tick_to_opportunity_seconds

    ref = MarketRef(market_id=UUID(int=1), exchange=EXCHANGE, symbol="SYM000USDT")

    class Refusing(MultiMarketHotState):
        async def zadd(self, key: str, mapping: dict[str, float]) -> int:
            raise ConnectionError("redis said no")

    redis = Refusing()
    redis.seed([ref], as_of=CUT)
    evaluation = _scored_evaluation(ref)
    before = _samples(scanner_tick_to_opportunity_seconds)

    assert (
        await projections.publish_radar(cast("Any", redis), ref, evaluation)
        == projections.RADAR_FAILED
    )
    assert _samples(scanner_tick_to_opportunity_seconds) == before


def _scored_evaluation(ref: MarketRef) -> Any:
    """The smallest evaluation ``publish_radar`` accepts as publishable."""
    from types import SimpleNamespace

    from hunter_core.domain.enums import OpportunityStage, OpportunityStatus, TradeDirection

    state = SimpleNamespace(
        score=Decimal("42.00"),
        status=OpportunityStatus.HOT,
        stage=OpportunityStage.NONE,
        direction=TradeDirection.LONG,
    )
    return SimpleNamespace(
        score=SimpleNamespace(score=Decimal("42.00"), confidence=Decimal("0.5"), eligible=True),
        status=SimpleNamespace(state_out=state),
        observation_ts=CUT,
        scored=True,
    )
