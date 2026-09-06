"""End to end with fakes: hot state -> features -> anomaly -> stage -> score -> radar.

The point of these tests is that they go through the *real* path -- the msgpack
rows a market-worker writes, ``read_hot_state``, the decoders, the engines of
``hunter_indicators`` and the batch builder -- so what they prove holds for the
process that runs in production. The only fakes are Redis and the clock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest

from hunter_core.domain.enums import BaselineSampling, BaselineSource
from hunter_indicators.baselines import (
    ALGO_VERSION,
    BaselineKey,
    BaselineRevision,
    StoredBaseline,
)
from hunter_indicators.features import Quality, Reason
from hunter_scanner_worker.baselines import BaselineCache
from hunter_scanner_worker.config import ScannerConfig
from hunter_scanner_worker.coverage import read_coverage
from hunter_scanner_worker.persist import WriteBatch
from hunter_scanner_worker.registry import MarketRegistry
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.state import ScannerState

from .builders import EXCHANGE, MARKET_ID, ORIGIN, REF, SYMBOL, FakeHotState, series
from .policies import build_policy

CUT = ORIGIN + timedelta(minutes=1500)


def _revision(feature: str, hour: int, *, median: str, mad: str, samples: int) -> StoredBaseline:
    window_end = CUT.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    return StoredBaseline(
        baseline_id=UUID(int=hash((feature, hour)) & ((1 << 128) - 1)),
        revision=BaselineRevision(
            key=BaselineKey(market_id=MARKET_ID, feature=feature, hour_of_day=hour),
            feature_version=1,
            algo_version=ALGO_VERSION,
            window_start=window_end - timedelta(days=7),
            window_end=window_end,
            available_at=window_end,
            median=Decimal(median),
            mad=Decimal(mad),
            sample_size=samples,
            expected_size=420,
            distinct_days=7,
            coverage=Decimal(samples) / Decimal(420),
            source=BaselineSource.LIVE,
            sampling=BaselineSampling.PER_MINUTE,
            input_fingerprint=f"{feature}:{hour}",
        ),
    )


def _scanner(*, entries: tuple[StoredBaseline, ...] = ()) -> Scanner:
    policy = build_policy()
    scanner = Scanner(
        config=ScannerConfig(exchange=EXCHANGE),
        policy=policy,
        registry=MarketRegistry(exchange=EXCHANGE),
        state=ScannerState(),
    )
    scanner.registry.apply([REF])
    scanner.cache = BaselineCache(gate=policy.gate, entries={MARKET_ID: entries})
    scanner.state.ensure(REF)
    return scanner


async def _advance(scanner: Scanner, redis: Any, *, now: datetime = CUT) -> Any:
    market = scanner.state.markets[SYMBOL]
    market.touch("tick", input_ts=now)
    scanner.coverage = await read_coverage(redis, EXCHANGE, now=now)
    batch = WriteBatch()
    evaluation = await scanner.advance(redis, market, batch, now=now)
    return evaluation, batch


@pytest.fixture
def hot_state() -> FakeHotState:
    state = FakeHotState()
    state.load(candles=series(1500), as_of=CUT)
    state.publish_coverage(session_since=ORIGIN, covered_until=CUT)
    return state


async def test_a_synthetic_market_produces_a_vector_a_score_and_a_radar_row(
    hot_state: FakeHotState,
) -> None:
    scanner = _scanner(
        entries=(
            _revision("relative_volume_5m", CUT.hour, median="1", mad="0.1", samples=400),
            _revision("momentum_15m", CUT.hour, median="0", mad="0.5", samples=400),
        )
    )

    evaluation, batch = await _advance(scanner, hot_state)

    assert evaluation is not None
    # The vector went through the real decoders: a feature that only exists if
    # the candles were parsed is present and usable.
    assert evaluation.vector.values["return_1m"].quality is Quality.OK
    assert evaluation.score is not None
    assert evaluation.status is not None
    # One row per closed minute, not one per tick.
    assert len(batch.snapshots) == 1
    assert batch.snapshots[0]["ts"] == CUT.replace(second=0, microsecond=0)


async def test_the_stored_envelope_keeps_the_vector_where_the_api_reads_it(
    hot_state: FakeHotState,
) -> None:
    scanner = _scanner(
        entries=(_revision("relative_volume_5m", CUT.hour, median="1", mad="0.1", samples=400),)
    )
    market = scanner.state.markets[SYMBOL]
    # Force an episode so an opportunity row is actually built.
    evaluation, _batch = await _advance(scanner, hot_state)
    assert evaluation is not None

    from hunter_scanner_worker.rows import storage_envelope

    envelope = storage_envelope(evaluation)

    # ``apps/api/.../radar_common.py`` (commit 98bcfea) reads
    # ``feature_snapshot["vector"]["values"][key]["value"]`` -- the key the
    # engine's own envelope uses. Renaming it here, as an earlier revision of
    # ``rows.py`` did, silently breaks the radar's volatility filter and volume
    # sort (Astra, T2.5 diff review).
    from hunter_api.repositories.radar_common import FEATURE_ENVELOPE_PATH

    outer, inner = FEATURE_ENVELOPE_PATH
    assert outer in envelope, f"the API reads {outer!r} and the envelope has {sorted(envelope)}"
    assert inner in envelope[outer]
    assert "atr_14_pct" in envelope[outer][inner]
    # And the history mark rides along without shadowing anything the API names.
    assert "history_mark" not in FEATURE_ENVELOPE_PATH
    assert market.checkpoint.features.atr_15m is not None


async def test_without_the_collectors_proof_the_tape_features_refuse_to_publish() -> None:
    state = FakeHotState()
    state.load(candles=series(1500), as_of=CUT)
    # No coverage hash at all: the collector proved nothing.
    scanner = _scanner()

    evaluation, _ = await _advance(scanner, state)

    assert evaluation is not None
    for key in ("trade_velocity_1m", "buy_pressure_5m", "sell_pressure_5m"):
        value = evaluation.vector.values[key]
        assert value.quality is Quality.UNAVAILABLE
        assert value.reason is Reason.INSUFFICIENT_COVERAGE


async def test_the_proof_releases_the_tape_features(hot_state: FakeHotState) -> None:
    scanner = _scanner()

    evaluation, _ = await _advance(scanner, hot_state)

    assert evaluation is not None
    velocity = evaluation.vector.values["trade_velocity_1m"]
    # This is the whole point of ``covered_until``: with the collector's proof
    # the same tape produces a number, and without it the same tape produces a
    # reason. Neither is a zero.
    assert velocity.quality is Quality.OK
    assert velocity.value is not None
    assert evaluation.vector.values["buy_pressure_5m"].quality is Quality.OK


async def test_the_minute_is_rebuilt_until_it_commits_and_only_then_stops(
    hot_state: FakeHotState,
) -> None:
    """One row per closed minute -- but the *promotion* waits for the commit.

    Marking the minute as written while building the batch loses it for good if
    the batch then fails: the batch is discarded whole and no later evaluation
    re-creates that minute (Astra, T2.5 diff review). So an uncommitted batch
    rebuilds it, the upsert on ``(market_id, ts)`` absorbs the repeat, and only
    the post-commit callback stops it.
    """
    scanner = _scanner()
    _, first = await _advance(scanner, hot_state, now=CUT)
    assert len(first.snapshots) == 1

    market = scanner.state.markets[SYMBOL]
    market.touch("tick", input_ts=CUT)
    retry = WriteBatch()
    await scanner.advance(cast("Any", hot_state), market, retry, now=CUT + timedelta(seconds=30))
    assert len(retry.snapshots) == 1, "an uncommitted minute has to be rebuilt"
    assert retry.snapshots[0]["ts"] == first.snapshots[0]["ts"]

    for _market_id, callback in retry.after_commit:
        callback()

    market.touch("tick", input_ts=CUT)
    after = WriteBatch()
    await scanner.advance(cast("Any", hot_state), market, after, now=CUT + timedelta(seconds=45))
    assert after.snapshots == [], "a committed minute is not written twice"


async def test_the_throttle_lets_features_run_without_the_score(
    hot_state: FakeHotState,
) -> None:
    scanner = _scanner()
    await _advance(scanner, hot_state, now=CUT)

    market = scanner.state.markets[SYMBOL]
    market.touch("tick", input_ts=CUT)
    batch = WriteBatch()
    evaluation = await scanner.advance(
        cast("Any", hot_state), market, batch, now=CUT + timedelta(seconds=1)
    )

    assert evaluation is not None
    # One second later the feature throttle has elapsed and the score throttle
    # (2 s) has not: the vector is fresh, the score deliberately is not.
    assert evaluation.score is None
    assert evaluation.stage is not None


def test_the_evaluation_cut_never_runs_ahead_of_the_proof() -> None:
    from hunter_scanner_worker.context import evaluation_cut
    from hunter_scanner_worker.coverage import TapeCoverage

    coverage = TapeCoverage(
        session_since=ORIGIN,
        covered_until=CUT - timedelta(milliseconds=500),
        symbols={SYMBOL: ORIGIN},
    )

    as_of, _, covered_until = evaluation_cut(coverage, SYMBOL, now=CUT)

    assert as_of == covered_until
    assert as_of < CUT
    assert as_of.tzinfo is UTC


async def test_a_regime_newer_than_the_cut_is_withheld_instead_of_raising(
    hot_state: FakeHotState,
) -> None:
    """The regime runs on its own minute loop while a market is evaluated at the
    collector's proven instant, so the regime can legitimately be a few seconds
    newer. ``ScoreContext`` refuses evidence from after the cut -- correctly --
    and the operational proof showed that refusal taking a whole cycle down."""
    from hunter_indicators.regime import RegimeThresholds
    from hunter_scanner_worker.regime import RegimeEngine

    scanner = _scanner()
    engine = RegimeEngine(thresholds=RegimeThresholds())
    scanner.regime = engine
    engine.seed([], until=CUT)
    engine.classify(
        vector=None,
        as_of=CUT + timedelta(seconds=30),
        breadth_observations=[],
        universe_size=1,
    )

    assert engine.last_decision is not None
    assert engine.last_decision.observation_ts > CUT
    # Withheld, not passed and not raised: the regime component has no reading
    # for this observation, which the scorer reports rather than filling in.
    assert scanner.regime_for(CUT) is None
    assert scanner.regime_for(CUT + timedelta(minutes=1)) is engine.last_decision

    evaluation, _ = await _advance(scanner, hot_state, now=CUT)
    assert evaluation is not None
    assert evaluation.score is not None
