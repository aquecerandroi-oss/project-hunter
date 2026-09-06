"""The watchdog, the restart and the universe -- the three ways state is lost.

Each test here fixes a guarantee the pure engines explicitly refused to make on
their own, because a pure function may not read a clock:

- ``anomalies.lifecycle`` cannot know that five readings span an hour, so the
  absolute expiry only fires if somebody reports the silence;
- ``opportunity.status`` cannot know that fourteen of its sixteen observations
  are missing, so the fifteen-minute expiry is only "proven" if somebody breaks
  the run;
- neither survives a restart unless the scanner reloads them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hunter_core.domain.enums import (
    AnomalyEvaluationState,
    AnomalyStatus,
    AnomalyType,
    OpportunityStage,
    OpportunityStatus,
    TradeDirection,
)
from hunter_indicators.anomalies import AnomalyDirection, AnomalyState
from hunter_indicators.opportunity import EpisodeState
from hunter_indicators.stage import StageState
from hunter_scanner_worker.checkpoint import (
    Checkpoint,
    history_mark_from_wire,
    stage_state_from_wire,
)
from hunter_scanner_worker.config import ScannerConfig
from hunter_scanner_worker.persist import WriteBatch
from hunter_scanner_worker.registry import MarketRegistry
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.state import ScannerState
from hunter_scanner_worker.watchdog import sweep_silent_markets

from .builders import EXCHANGE, MARKET_ID, REF, SYMBOL
from .policies import build_policy

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _scanner() -> Scanner:
    scanner = Scanner(
        config=ScannerConfig(exchange=EXCHANGE),
        policy=build_policy(),
        registry=MarketRegistry(exchange=EXCHANGE),
        state=ScannerState(),
    )
    scanner.registry.apply([REF])
    scanner.state.ensure(REF, now=NOW - timedelta(hours=1))
    return scanner


def _open_anomaly(*, observed: datetime, detected: datetime) -> AnomalyState:
    return AnomalyState(
        market_id=MARKET_ID,
        type=AnomalyType.VOLUME_SPIKE,
        status=AnomalyStatus.ACTIVE,
        evaluation_state=AnomalyEvaluationState.OK,
        detected_at=detected,
        observation_ts=observed,
        severity=Decimal("80"),
        confidence=Decimal("0.9"),
        direction=AnomalyDirection.UP,
        below_hold_since=observed,
        below_hold_readings=4,
    )


def test_the_watchdog_reports_silence_and_zeroes_the_proven_calm_counters() -> None:
    scanner = _scanner()
    market = scanner.state.markets[SYMBOL]
    market.anomalies = {
        AnomalyType.VOLUME_SPIKE: _open_anomaly(
            observed=NOW - timedelta(minutes=10), detected=NOW - timedelta(hours=1)
        )
    }
    market.anomaly_ids = {AnomalyType.VOLUME_SPIKE: MARKET_ID}
    market.last_observation_ts = NOW - timedelta(minutes=10)
    batch = WriteBatch()

    report = sweep_silent_markets(scanner, batch, now=NOW)

    assert report.silent == 1
    state = market.anomalies[AnomalyType.VOLUME_SPIKE]
    # Four readings below the holding line do not survive a gap: a market we
    # could not see is not a market that was calm.
    assert state.below_hold_readings == 0
    assert state.evaluation_state is not AnomalyEvaluationState.OK
    assert batch.anomalies, "the state change has to reach the row"


def test_an_anomaly_nobody_can_evaluate_stays_active_and_is_never_resolved() -> None:
    scanner = _scanner()
    market = scanner.state.markets[SYMBOL]
    market.anomalies = {
        AnomalyType.VOLUME_SPIKE: _open_anomaly(
            observed=NOW - timedelta(minutes=5), detected=NOW - timedelta(minutes=30)
        )
    }
    market.anomaly_ids = {AnomalyType.VOLUME_SPIKE: MARKET_ID}
    market.last_observation_ts = NOW - timedelta(minutes=5)

    sweep_silent_markets(scanner, WriteBatch(), now=NOW)

    state = market.anomalies[AnomalyType.VOLUME_SPIKE]
    # "We stopped looking" is not "it stopped happening" (DATABASE.md 17.4).
    assert state.status is AnomalyStatus.ACTIVE


def test_the_absolute_expiry_fires_once_the_silence_is_reported() -> None:
    scanner = _scanner()
    market = scanner.state.markets[SYMBOL]
    market.anomalies = {
        AnomalyType.VOLUME_SPIKE: _open_anomaly(
            observed=NOW - timedelta(hours=5), detected=NOW - timedelta(hours=5)
        )
    }
    market.anomaly_ids = {AnomalyType.VOLUME_SPIKE: MARKET_ID}
    market.last_observation_ts = NOW - timedelta(hours=5)

    sweep_silent_markets(scanner, WriteBatch(), now=NOW)

    # Four hours is not a timer that runs by itself; it is a verdict something
    # has to ask for.
    assert market.anomalies[AnomalyType.VOLUME_SPIKE].status is AnomalyStatus.EXPIRED
    assert AnomalyType.VOLUME_SPIKE not in market.anomaly_ids


def test_a_blind_interval_breaks_the_expiry_run_without_expiring_the_episode() -> None:
    scanner = _scanner()
    market = scanner.state.markets[SYMBOL]
    market.opportunity_id = MARKET_ID
    market.episode = EpisodeState(
        status=OpportunityStatus.WATCHING,
        first_seen_at=NOW - timedelta(hours=2),
        observation_ts=NOW - timedelta(minutes=10),
        score=Decimal("35.00"),
        peak_score=Decimal("80.00"),
        stage=OpportunityStage.DEVELOPING,
        direction=TradeDirection.LONG,
        below_floor_since=NOW - timedelta(minutes=14),
        below_floor_readings=14,
    )
    market.last_observation_ts = NOW - timedelta(minutes=10)
    batch = WriteBatch()

    sweep_silent_markets(scanner, batch, now=NOW)

    assert market.episode is not None
    # Fourteen minutes below the floor plus ten blind minutes are not fifteen
    # proven minutes: the run restarts and the episode stays open.
    assert market.episode.below_floor_since is None
    assert market.episode.below_floor_readings == 0
    assert market.episode.expired_at is None
    assert batch.episode_touches and batch.episode_touches[0]["expired_at"] is None


def test_a_stage_state_survives_a_restart_through_the_checkpoint() -> None:
    published = StageState(
        stage=OpportunityStage.EARLY,
        basis="ratio",
        candidate=OpportunityStage.DEVELOPING,
        confirmations=1,
        last_observation_ts=NOW,
        direction=TradeDirection.LONG,
        candidate_direction=TradeDirection.SHORT,
        unsupported=1,
    )

    restored = stage_state_from_wire(published.as_wire())

    # Every counter, including the side of the *published* stage: a scanner that
    # came back saying NEUTRAL for an EARLY long would repaint it on the next
    # observation (notes-T2.3, cross review (a)).
    assert restored == published


def test_a_history_mark_survives_a_restart_so_the_sampling_rule_has_a_baseline() -> None:
    from hunter_indicators.opportunity import HistoryMark

    mark = HistoryMark(
        ts=NOW,
        score=Decimal("62.00"),
        status=OpportunityStatus.WATCHING,
        stage=OpportunityStage.DEVELOPING,
        direction=TradeDirection.LONG,
        stage_direction=TradeDirection.LONG,
        regime="bull/normal",
        quality="momentum:1:3/3",
        versions={"weights": "v2"},
    )

    restored = history_mark_from_wire(mark.as_wire())

    assert restored == mark


def test_a_checkpoint_that_was_never_written_starts_cold_and_says_so() -> None:
    checkpoint = Checkpoint()

    # ``advance_from_context`` reports "bootstrap" for both a first start and a
    # lost checkpoint, so the distinction has to live here or nobody can tell an
    # operator which one happened (Astra, T2.5 design review).
    assert checkpoint.recovered is False
    assert checkpoint.features.atr_15m is None
    assert checkpoint.history is None


def test_a_market_that_left_the_universe_stops_being_evaluated() -> None:
    scanner = _scanner()
    assert SYMBOL in scanner.state.markets

    diff = scanner.registry.apply([])
    for ref in diff.removed:
        scanner.state.drop(ref.symbol)

    assert scanner.state.markets == {}
    assert diff.removed and diff.removed[0].symbol == SYMBOL


def test_every_long_lived_component_can_actually_be_constructed() -> None:
    """Constructing the scanner's own objects, which no unit test did.

    The operational proof caught ``deque[NormalizedCandle](maxlen=...)`` inside a
    ``default_factory``: the subscript is evaluated at runtime and the candle
    type is a ``TYPE_CHECKING``-only import, so the worker died at startup while
    every test passed. Anything built once at startup gets built here.
    """
    from hunter_scanner_worker.backfill import BackfillRequester
    from hunter_scanner_worker.baselines import BaselineCache
    from hunter_scanner_worker.consumers import ConsumerHealth
    from hunter_scanner_worker.health import CycleHealth
    from hunter_scanner_worker.regime import RegimeEngine
    from hunter_scanner_worker.state import MarketState

    policy = build_policy()
    engine = RegimeEngine(thresholds=policy.regime)
    assert engine.candles.maxlen is not None
    assert MarketState(ref=REF).rv15_closes.maxlen == 4
    assert BaselineCache(gate=policy.gate).entries == {}
    assert ConsumerHealth().errors == 0
    assert CycleHealth().baselines_loaded is False
    assert BackfillRequester("scanner-worker@test") is not None


def test_every_metric_is_on_the_registry_that_is_actually_scraped() -> None:
    """``/metrics`` exposes ``hunter_core.observability.registry``, not the
    prometheus_client default. A metric declared without it is collected into a
    registry nobody scrapes -- the operational proof found ``/metrics`` answering
    200 with not one ``scanner_`` line in it."""
    from hunter_core.observability import registry
    from hunter_scanner_worker import metrics

    # The *declared* families, not the samples: a labelled metric emits no
    # sample until some label combination is used, and "declared on the right
    # registry" is exactly what this test is about.
    exposed = {family.name for family in registry.collect()}
    for name in metrics.__all__:
        metric = getattr(metrics, name)
        # ``_name`` is where prometheus_client keeps the registered family name.
        declared = metric._name
        assert any(item == declared or declared.startswith(item) for item in exposed), (
            f"{name} is not on the scraped registry"
        )
