"""Turning one :class:`Evaluation` into batch entries. Split from ``scanner.py``
for the 350-line budget, and the seam is where it belongs: this module knows the
shape of a batch, ``Scanner`` knows the shape of a cycle.

Every entry is tagged with the market that produced it (``event_market``,
``after_commit``), because a batch can lose one evaluation without losing the
others: a baseline that vanished under a sample invalidates *that* market, and
its events and post-commit promotions have to go down with its rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from hunter_core.domain.enums import AnomalyStatus
from hunter_core.domain.types import uuid7
from hunter_core.events.outbox import build_envelope, event_id_for
from hunter_core.events.streams import Streams
from hunter_indicators.anomalies import AnomalyAction
from hunter_indicators.opportunity import EpisodeAction
from hunter_scanner_worker import rows
from hunter_scanner_worker.checkpoint import Checkpoint

if TYPE_CHECKING:
    from hunter_indicators.opportunity import HistoryMark
    from hunter_scanner_worker.evaluate import Evaluation
    from hunter_scanner_worker.persist import WriteBatch
    from hunter_scanner_worker.state import MarketState

__all__ = [
    "collect_anomalies",
    "collect_opportunity",
    "collect_snapshot",
    "promote_snapshot",
    "remember_history",
]


def collect_snapshot(market: MarketState, evaluation: Evaluation, batch: WriteBatch) -> None:
    """One row per closed minute -- never one per tick."""
    minute = evaluation.observation_ts.replace(second=0, microsecond=0)
    if market.last_snapshot_minute is not None and minute <= market.last_snapshot_minute:
        return
    batch.snapshots.append(
        rows.feature_snapshot_row(market.ref.market_id, evaluation.vector, minute)
    )
    # **After** the commit, never here: a failed batch is discarded whole, and a
    # minute already marked as written would never be re-created -- the row would
    # be lost for good (Astra, T2.5 diff review). Until it commits the same
    # minute is simply rebuilt, and the upsert on ``(market_id, ts)`` absorbs it.
    batch.after_commit.append((market.ref.market_id, lambda: promote_snapshot(market, minute)))


def promote_snapshot(market: MarketState, minute: datetime) -> None:
    """The minute is written; stop rebuilding it."""
    if market.last_snapshot_minute is None or minute > market.last_snapshot_minute:
        market.last_snapshot_minute = minute


def remember_history(market: MarketState, mark: HistoryMark) -> None:
    """After the commit, the persisted sample is the one the rule compares to."""
    market.checkpoint = Checkpoint(
        features=market.checkpoint.features,
        stage=market.checkpoint.stage,
        history=mark,
        recovered=market.checkpoint.recovered,
    )


def collect_anomalies(
    producer: str,
    market: MarketState,
    evaluation: Evaluation,
    batch: WriteBatch,
    *,
    now: datetime,
) -> None:
    """Rows and announcements for every lifecycle transition of one market."""
    for transition in evaluation.transitions:
        state = transition.state
        if state is None or transition.action is AnomalyAction.NONE:
            continue
        anomaly_id = market.anomaly_ids.get(state.type)
        if anomaly_id is None or transition.action is AnomalyAction.OPEN:
            anomaly_id = uuid7()
            market.anomaly_ids[state.type] = anomaly_id
        batch.anomalies.append(rows.anomaly_row(state, anomaly_id=anomaly_id))
        batch.reference(market.ref.market_id, state.baseline_ids)
        if transition.action in (AnomalyAction.OPEN, AnomalyAction.UPDATE):
            payload = rows.anomaly_event_payload(
                state, anomaly_id=anomaly_id, action=transition.action.value
            )
            envelope = build_envelope(
                Streams.ANOMALIES_DETECTED,
                event_id_for(
                    Streams.ANOMALIES_DETECTED,
                    anomaly_id,
                    state.observation_ts,
                    transition.action.value,
                ),
                payload,
                producer=producer,
                key=f"{market.ref.exchange}:{market.ref.symbol}",
                ts=now,
            )
            batch.events.append(envelope)
            batch.event_market[envelope.event_id] = market.ref.market_id
        if state.status is not AnomalyStatus.ACTIVE:
            market.anomaly_ids.pop(state.type, None)
            market.closed_anomaly_at[state.type] = state.observation_ts


def collect_opportunity(
    producer: str,
    regime_id: UUID | None,
    market: MarketState,
    evaluation: Evaluation,
    batch: WriteBatch,
    *,
    now: datetime,
) -> None:
    """The episode row, its preserved sample and the event that announces both."""
    decision = evaluation.status
    if decision is None or evaluation.score is None:
        return
    market.episode = decision.state_out
    if decision.state_out is None or decision.action is EpisodeAction.NONE:
        return
    opportunity_id = market.opportunity_id or uuid7()
    market.opportunity_id = opportunity_id
    batch.reference(market.ref.market_id, evaluation.baseline_ids)
    batch.opportunities.append(
        rows.opportunity_row(
            evaluation,
            opportunity_id=opportunity_id,
            regime_id=regime_id,
            anomaly_ids=sorted(market.anomaly_ids.values()),
            now=now,
        )
    )
    mark = evaluation.history_mark
    if evaluation.history is not None and evaluation.history.record and mark is not None:
        batch.history.append(rows.history_row(evaluation, opportunity_id=opportunity_id))
        batch.after_commit.append((market.ref.market_id, lambda: remember_history(market, mark)))
    announcement = build_envelope(
        Streams.OPPORTUNITIES_UPDATED,
        event_id_for(
            Streams.OPPORTUNITIES_UPDATED,
            opportunity_id,
            evaluation.observation_ts,
            decision.action.value,
        ),
        rows.opportunity_event_payload(
            evaluation, opportunity_id=opportunity_id, action=decision.action.value
        ),
        producer=producer,
        key=f"{market.ref.exchange}:{market.ref.symbol}",
        ts=now,
    )
    batch.events.append(announcement)
    batch.event_market[announcement.event_id] = market.ref.market_id
    if decision.action is EpisodeAction.EXPIRE:
        # The episode is over: the next one is a new row with a new id, and
        # forgetting the id here is what makes that true.
        market.opportunity_id = None
        market.episode = None
