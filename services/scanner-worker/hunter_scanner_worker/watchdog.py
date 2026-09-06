"""Telling the pure engines about the minutes nobody saw.

Both state machines were written to refuse inferring a gap, and both said so in
writing: ``anomalies.lifecycle`` counts *readings* below the holding line and
cannot know that five of them span an hour rather than five minutes
(notes-T2.3 section 16), and ``opportunity.status`` proves its fifteen-minute
expiry with sixteen observations and cannot know that fourteen of them are
missing (notes-T2.4 section 5). Neither may read a clock: a pure function that
looked at ``utcnow()`` would stop being replayable.

So the absence is *reported*, here, and this is the module that makes those two
guarantees true rather than intended:

- a market with no fresh vector gets ``no_data`` fed to every detector, which
  zeroes the proven-calm counters and lets the four-hour absolute expiry
  actually fire;
- and an **ineligible** status sample, which breaks the below-floor run without
  expiring anything -- four minutes below the floor, ten minutes blind and one
  more are not fifteen proven minutes.

Both are the same statement: a market we could not see is not a market that was
calm.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_indicators.anomalies import DEFAULT_DETECTORS, advance_all, no_data
from hunter_indicators.opportunity import StatusSample, advance_status
from hunter_scanner_worker import rows
from hunter_scanner_worker.evaluate import next_anomaly_states

if TYPE_CHECKING:
    from hunter_scanner_worker.persist import WriteBatch
    from hunter_scanner_worker.scanner import Scanner
    from hunter_scanner_worker.state import MarketState

logger = get_logger(__name__)

SILENCE_S = 120.0
"""How long a market may go without a vector before it is declared unobserved.

Two minutes, not one: a single missed cycle under load is not an outage, and
declaring one would zero counters that were legitimately accumulating.
"""

__all__ = ["SILENCE_S", "WatchdogReport", "sweep_silent_markets"]


@dataclass(frozen=True, slots=True)
class WatchdogReport:
    silent: int = 0
    anomalies_touched: int = 0
    episodes_touched: int = 0


def _silent(market: MarketState, now: datetime, silence_s: float) -> bool:
    last = market.last_observation_ts or market.joined_at
    if last is None:
        return False
    return now - last > timedelta(seconds=silence_s)


def sweep_silent_markets(
    scanner: Scanner,
    batch: WriteBatch,
    *,
    now: datetime | None = None,
    silence_s: float = SILENCE_S,
) -> WatchdogReport:
    """Feed the absence to both machines, for every market that went quiet."""
    moment = now or utcnow()
    silent = 0
    anomalies_touched = 0
    episodes_touched = 0
    for market in list(scanner.state.markets.values()):
        if not _silent(market, moment, silence_s):
            continue
        silent += 1
        anomalies_touched += _expire_anomalies(scanner, market, batch, now=moment)
        episodes_touched += _break_episode_run(scanner, market, batch, now=moment)
        market.last_observation_ts = moment
    if silent:
        logger.info(
            "scanner_watchdog_swept",
            silent=silent,
            anomalies=anomalies_touched,
            episodes=episodes_touched,
        )
    return WatchdogReport(
        silent=silent, anomalies_touched=anomalies_touched, episodes_touched=episodes_touched
    )


def _expire_anomalies(
    scanner: Scanner, market: MarketState, batch: WriteBatch, *, now: datetime
) -> int:
    open_states = [state for state in market.anomalies.values() if state.is_open]
    if not open_states:
        return 0
    definitions = {definition.type: definition for definition in DEFAULT_DETECTORS}
    evaluations = [
        no_data(market.ref.market_id, definitions[state.type], observation_ts=now)
        for state in open_states
        if state.type in definitions
    ]
    if not evaluations:
        return 0
    transitions = advance_all(open_states, evaluations, DEFAULT_DETECTORS)
    market.anomalies = {
        state.type: state
        for state in next_anomaly_states(tuple(market.anomalies.values()), transitions)
    }
    touched = 0
    for transition in transitions:
        state = transition.state
        if state is None:
            continue
        anomaly_id = market.anomaly_ids.get(state.type)
        if anomaly_id is None:
            continue
        batch.anomalies.append(rows.anomaly_row(state, anomaly_id=anomaly_id))
        touched += 1
        if not state.is_open:
            market.anomaly_ids.pop(state.type, None)
            market.closed_anomaly_at[state.type] = state.observation_ts
    return touched


def _break_episode_run(
    scanner: Scanner, market: MarketState, batch: WriteBatch, *, now: datetime
) -> int:
    """An ineligible sample: it breaks the run, it never expires the episode."""
    if market.episode is None or market.opportunity_id is None:
        return 0
    decision = advance_status(
        market.episode,
        StatusSample(observation_ts=now, score=None, eligible=False),
        scanner.policy.status,
    )
    market.episode = decision.state_out
    if decision.state_out is None:
        return 0
    # Only the durable counters move; the score, the decomposition and the
    # envelope are untouched, because nothing was observed to change them.
    batch.episode_touches.append(
        {
            "id": market.opportunity_id,
            "market_id": market.ref.market_id,
            "below_40_since": decision.state_out.below_floor_since,
            "status": decision.state_out.status,
            "expired_at": decision.state_out.expired_at,
            "last_updated_at": now,
        }
    )
    return 1
