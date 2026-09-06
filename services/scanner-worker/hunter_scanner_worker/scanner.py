"""The scanner itself: shared components, and one market advanced by one cut.

``Scanner`` owns everything a cycle needs -- the registry, the per-market states,
the versioned policy, the baseline cache, the regime engine and the coverage
proof -- and exposes the one operation everything else is built out of:
:meth:`Scanner.advance`, which takes one market from "dirty" to a committed-ready
set of rows and events.

Keeping that in one place is not tidiness, it is the correctness argument: the
score, the stage, the anomalies and the regime have to describe the same instant
(``ScoreContext`` refuses otherwise), and the only way to guarantee that is for
one owner to resolve them together.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from hunter_core.domain.enums import AnomalyStatus, RegimeScope
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_indicators.baselines import BaselineCut
from hunter_indicators.features import Quality
from hunter_indicators.regime import RegimeDecision
from hunter_indicators.stage import StageInputs
from hunter_scanner_worker import collect
from hunter_scanner_worker.baselines import BaselineCache
from hunter_scanner_worker.checkpoint import Checkpoint
from hunter_scanner_worker.context import build_market_context
from hunter_scanner_worker.coverage import TapeCoverage
from hunter_scanner_worker.deriv import DerivHistory, detector_roster, disarmed_reasons
from hunter_scanner_worker.evaluate import Evaluation, EvaluationInputs, evaluate_market
from hunter_scanner_worker.metrics import (
    scanner_markets_evaluated_total,
    scanner_tick_to_opportunity_seconds,
)
from hunter_scanner_worker.persist import WriteBatch
from hunter_scanner_worker.regime import RegimeEngine
from hunter_scanner_worker.registry import MarketRegistry
from hunter_scanner_worker.state import MarketState, ScannerState

if TYPE_CHECKING:
    from collections.abc import Sequence

    import redis.asyncio as redis_asyncio

    from hunter_scanner_worker.config import ScannerConfig
    from hunter_scanner_worker.policy import Policy

logger = get_logger(__name__)

TRADE_VELOCITY_FEATURE = "trade_velocity_1m"
RELATIVE_VOLUME_15M = "relative_volume_15m"
BAR_MINUTES = 15

__all__ = ["Scanner"]


@dataclass
class Scanner:
    """Everything shared across cycles, and the per-market advance."""

    config: ScannerConfig
    policy: Policy
    registry: MarketRegistry
    state: ScannerState = field(default_factory=ScannerState)
    cache: BaselineCache | None = None
    regime: RegimeEngine | None = None
    coverage: TapeCoverage = field(default_factory=TapeCoverage)
    deriv: DerivHistory = field(default_factory=DerivHistory)
    """Open-interest readings from the durable tables. Without them the
    ``open_interest_change_*`` features are ``missing_input`` forever and
    ``OPEN_INTEREST_SPIKE`` is armed and permanently silent."""

    regime_id: UUID | None = None
    producer: str = "scanner-worker"

    # --- inputs ------------------------------------------------------------

    def stage_inputs(self, market: MarketState, *, as_of: datetime) -> StageInputs:
        """What the vector does not carry: the tape baseline and the 15m closes.

        Both are resolved by the caller precisely so the classifier stays pure,
        and both travel into the stored envelope -- "the confirmation fired"
        without the number it fired against is not reproducible (notes-T2.3,
        must-fix 5).
        """
        median = None
        if self.cache is not None:
            median = self.cache.median_of(market.ref.market_id, TRADE_VELOCITY_FEATURE, as_of.hour)
        closes = tuple(value for _, value in market.rv15_closes)
        return StageInputs(trade_velocity_baseline=median, relative_volume_15m_closes=closes)

    def _record_bar_close(self, market: MarketState, evaluation: Evaluation) -> None:
        """Sample ``relative_volume_15m`` once per completed 15-minute bar."""
        as_of = evaluation.observation_ts
        boundary = as_of.replace(second=0, microsecond=0) - timedelta(
            minutes=as_of.minute % BAR_MINUTES
        )
        if market.last_bar_close is not None and boundary <= market.last_bar_close:
            return
        entry = evaluation.vector.values.get(RELATIVE_VOLUME_15M)
        if entry is None or entry.quality is not Quality.OK or entry.value is None:
            # An unusable reading is not a zero and not a repeat of the last
            # one: the bar simply contributes no evidence, and the classifier
            # sees a shorter series (which it treats as "not enough").
            market.last_bar_close = boundary
            return
        market.rv15_closes.append((boundary, entry.value))
        market.last_bar_close = boundary

    # --- one market --------------------------------------------------------

    async def advance(
        self,
        redis: redis_asyncio.Redis,
        market: MarketState,
        batch: WriteBatch,
        *,
        now: datetime | None = None,
    ) -> Evaluation | None:
        """Evaluate one market and add everything it concluded to ``batch``."""
        moment = now or utcnow()
        if self.cache is None:
            return None
        observations = self.deriv.for_market(market.ref.market_id)
        build = await build_market_context(
            redis,
            exchange=market.ref.exchange,
            symbol=market.ref.symbol,
            coverage=self.coverage,
            deriv_history=observations,
            now=moment,
        )
        context = build.context
        # Rebuilt every cycle, from current state: that is what makes a detector
        # rearm by itself the moment its evidence exists, and what keeps
        # "cannot be evaluated" a *declared* state instead of silence.
        snapshot = context.deriv.value
        detectors = detector_roster(
            has_oi_history=bool(observations),
            has_funding=snapshot is not None and snapshot.funding_rate is not None,
        )
        market.disarmed = disarmed_reasons(detectors)
        cut = BaselineCut(as_of=context.as_of, observation_ts=context.as_of)
        score_due = market.due_for_score(moment, self.config.score_throttle_s)
        evaluation = evaluate_market(
            EvaluationInputs(
                market_id=market.ref.market_id,
                context=context,
                projection=self.cache.projection(market.ref.market_id, cut),
                profile=self.policy.profile,
                config=self.policy.normalization,
                stage_thresholds=self.policy.stage,
                status_thresholds=self.policy.status,
                stage_inputs=self.stage_inputs(market, as_of=context.as_of),
                detectors=detectors,
                stage_state=market.checkpoint.stage,
                feature_state=market.checkpoint.features,
                anomaly_states=tuple(market.anomalies.values()),
                episode=market.episode,
                regime=self.regime_for(context.as_of),
                regime_stale=bool(
                    self.regime is not None and self.regime.stale(as_of=context.as_of)
                ),
                regime_id=self.regime_id,
                last_history=market.checkpoint.history,
                score_due=score_due,
            )
        )
        self._collect(market, evaluation, batch, now=moment)
        market.last_vector = evaluation.vector
        market.last_vector_at = moment
        market.last_observation_ts = evaluation.observation_ts
        market.evaluations += 1
        if score_due:
            market.last_score_at = moment
            if market.last_input_ts is not None:
                scanner_tick_to_opportunity_seconds.observe(
                    max(0.0, (utcnow() - market.last_input_ts).total_seconds())
                )
        scanner_markets_evaluated_total.labels(
            outcome="covered" if build.covered else "uncovered"
        ).inc()
        market.clear_dirty()
        return evaluation

    # --- turning one evaluation into rows and events -----------------------

    def _collect(
        self, market: MarketState, evaluation: Evaluation, batch: WriteBatch, *, now: datetime
    ) -> None:
        self._record_bar_close(market, evaluation)
        market.checkpoint = Checkpoint(
            features=evaluation.features.state,
            stage=evaluation.stage.state_out
            if evaluation.stage is not None
            else market.checkpoint.stage,
            history=market.checkpoint.history,
            recovered=market.checkpoint.recovered,
        )
        market.anomalies = {state.type: state for state in evaluation.anomaly_states}
        collect.collect_snapshot(market, evaluation, batch)
        collect.collect_anomalies(self.producer, market, evaluation, batch, now=now)
        collect.collect_opportunity(
            self.producer, self.regime_id, market, evaluation, batch, now=now
        )

    def regime_for(self, as_of: datetime) -> RegimeDecision | None:
        """The regime this observation is allowed to see -- never a newer one.

        The regime runs on its own minute loop while a market is evaluated at
        the collector's proven instant, which is a few seconds behind; the two
        clocks are different by design. ``ScoreContext`` refuses evidence from
        after the cut (it is look-ahead), and it is right to: found in the
        operational proof, where a regime classified at ``utcnow()`` raised
        against a cut ~10 s older and took the whole cycle down.

        Withholding it is the honest answer, not a downgrade: the regime
        component simply has no reading for this observation, which the scorer
        already reports as unavailable rather than redistributing its weight.
        """
        if self.regime is None:
            return None
        decision = self.regime.last_decision
        if decision is None or decision.observation_ts > as_of:
            return None
        return decision

    def regime_scope(self) -> RegimeScope:
        return RegimeScope.GLOBAL

    def open_severity(self, market: MarketState) -> Decimal | None:
        severities = [
            state.severity
            for state in market.anomalies.values()
            if state.status is AnomalyStatus.ACTIVE
        ]
        return max(severities) if severities else None

    def refs(self) -> Sequence[UUID]:
        return [state.ref.market_id for state in self.state.markets.values()]
