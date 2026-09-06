"""Per-market runtime state and the dirty set that drives every cadence.

The joint M2 decision's cost rules are all here: an incremental context per
market (never 1500 candles re-read per tick), work driven by *dirty* markets
rather than by a full sweep, and coalescence — a market touched twenty times in
one second is evaluated once.

**One owner advances one market** (Astra, T2.5 design review). The consumers only
mark; the evaluation loop is the single writer of everything below, so a score is
never assembled from a stage that a different task already moved past. That is
also what makes ``ScoreContext``'s "one cut" check satisfiable at all.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from hunter_core.domain.enums import AnomalyType
from hunter_core.domain.types import utcnow
from hunter_scanner_worker.checkpoint import Checkpoint

if TYPE_CHECKING:
    from hunter_indicators.anomalies import AnomalyState
    from hunter_indicators.features import FeatureVector
    from hunter_indicators.opportunity import EpisodeState
    from hunter_scanner_worker.registry import MarketRef

__all__ = ["MarketState", "PendingAck", "ScannerState"]


@dataclass(frozen=True, slots=True)
class PendingAck:
    """A consumed message whose effect has not been committed yet.

    The ACK is what tells Redis the work is done, so it may not happen when the
    message is *read* — a crash between the two would lose the minute the message
    announced. Held here and acked by the persist cycle, after the transaction
    that contains its effect commits.
    """

    stream: str
    group: str
    message_id: str
    event_id: str


@dataclass
class MarketState:
    """Everything the evaluator carries between two observations of one market."""

    ref: MarketRef
    checkpoint: Checkpoint = field(default_factory=Checkpoint)
    anomalies: dict[AnomalyType, AnomalyState] = field(
        default_factory=dict[AnomalyType, "AnomalyState"]
    )
    closed_anomaly_at: dict[AnomalyType, datetime] = field(
        default_factory=dict[AnomalyType, datetime]
    )
    """When each ``(market, type)`` episode last ended. Kept because the
    lifecycle's ordering guard applies to closed states too: a restart that
    loaded only the *active* rows would let a replayed evaluation from before the
    end reopen an anomaly that is over (Astra, design review)."""

    anomaly_ids: dict[AnomalyType, UUID] = field(default_factory=dict[AnomalyType, UUID])
    """The row id of each open ``(market, type)`` episode, so an update targets
    the row it belongs to instead of racing the partial unique index."""

    episode: EpisodeState | None = None
    opportunity_id: UUID | None = None
    regime_id_used: UUID | None = None

    rv15_closes: deque[tuple[datetime, Decimal]] = field(
        default_factory=lambda: deque[tuple[datetime, Decimal]](maxlen=4)
    )
    """``relative_volume_15m`` at the last four 15-minute closes -- the exhaustion
    evidence ``StageInputs`` asks the caller for. Sampled at the boundary, not
    every second: the classifier compares *closes*, and feeding it intra-bar
    readings would make three strict falls a matter of when we happened to look.
    """

    last_bar_close: datetime | None = None

    dirty_since: datetime | None = None
    dirty_reasons: set[str] = field(default_factory=set[str])
    last_input_ts: datetime | None = None
    """Newest input timestamp that made this market dirty — the start of the
    tick->opportunity measurement."""

    last_vector: FeatureVector | None = None
    """The last vector computed for this market. Kept because the regime's
    breadth is built from vectors the cycle **already** computed -- recomputing
    200 of them once a minute would double the scanner's cost for a number that
    is already in hand."""

    last_vector_at: datetime | None = None
    last_score_at: datetime | None = None
    last_observation_ts: datetime | None = None
    last_snapshot_minute: datetime | None = None
    joined_at: datetime | None = None
    evaluations: int = 0

    baseline_note: str | None = None
    """Why this market's baselines are still "under construction", if they are.
    Set by the bootstrap when it finds holes it had to ask somebody else to
    repair; ``None`` once a run completed over an unbroken history."""

    disarmed: tuple[tuple[str, str], ...] = ()
    """``(detector, reason)`` for every detector this market cannot evaluate at
    all. An armed detector that can never fire is indistinguishable from a calm
    market, so the reason is carried here and reported."""

    def touch(self, reason: str, *, input_ts: datetime | None = None) -> None:
        """Mark dirty. Twenty touches in a second still cost one evaluation."""
        now = utcnow()
        if self.dirty_since is None:
            self.dirty_since = now
        self.dirty_reasons.add(reason)
        if input_ts is not None and (self.last_input_ts is None or input_ts > self.last_input_ts):
            self.last_input_ts = input_ts

    def clear_dirty(self) -> None:
        self.dirty_since = None
        self.dirty_reasons = set()
        self.last_input_ts = None

    def due_for_features(self, now: datetime, throttle_s: float) -> bool:
        if self.dirty_since is None:
            return False
        if self.last_vector_at is None:
            return True
        return now - self.last_vector_at >= timedelta(seconds=throttle_s)

    def due_for_score(self, now: datetime, throttle_s: float) -> bool:
        if self.last_score_at is None:
            return True
        return now - self.last_score_at >= timedelta(seconds=throttle_s)


@dataclass
class ScannerState:
    """The scanner's whole working set: one state per monitored market."""

    markets: dict[str, MarketState] = field(default_factory=dict[str, "MarketState"])
    pending_acks: list[PendingAck] = field(default_factory=list[PendingAck])

    def get(self, symbol: str) -> MarketState | None:
        return self.markets.get(symbol)

    def ensure(self, ref: MarketRef, *, now: datetime | None = None) -> MarketState:
        state = self.markets.get(ref.symbol)
        if state is None:
            state = MarketState(ref=ref, joined_at=now or utcnow())
            self.markets[ref.symbol] = state
        return state

    def drop(self, symbol: str) -> MarketState | None:
        """A market left the universe: its evaluation ends honestly, here."""
        return self.markets.pop(symbol, None)

    def touch(self, symbol: str, reason: str, *, input_ts: datetime | None = None) -> bool:
        state = self.markets.get(symbol)
        if state is None:
            return False
        state.touch(reason, input_ts=input_ts)
        return True

    @property
    def dirty(self) -> int:
        return sum(1 for state in self.markets.values() if state.dirty_since is not None)

    def due(self, now: datetime, throttle_s: float) -> list[MarketState]:
        """Dirty markets whose throttle has elapsed, oldest dirt first.

        Oldest first because the budget being defended is the *age* of the input,
        not the order of the symbols: under load the market that has been waiting
        longest is the one about to violate p99.
        """
        ready = [
            state for state in self.markets.values() if state.due_for_features(now, throttle_s)
        ]
        ready.sort(key=lambda state: state.dirty_since or now)
        return ready
