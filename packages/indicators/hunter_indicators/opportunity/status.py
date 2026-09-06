"""The episode machine: one status, one identity, one terminal end.

Pure, and driven by the ``observation_ts`` of the sample it is given — no clock,
so the scanner, a watchdog and a replay walk the same path. The caller owns the
row and the id; this function says what changed and why.

Precedence, highest first (``docs/plans/M2.md``, joint decision): ``EXPIRED``
(terminal) > ``EXTENDED`` > ``ENTRY_CANDIDATE`` > ``HOT`` > ``ANOMALY`` >
``WATCHING`` > ``NORMAL``. ``IN_POSITION`` and ``RISK_BLOCKED`` are derived per
organisation at read time and are deliberately absent.

Four rules, each with its reason:

- **``NORMAL`` never opens an episode, but is a valid state of an open one.** The
  decisive scenario is ``HOT(80) -> NORMAL(35) -> WATCHING(45)``: the same move,
  therefore the same id, therefore ``below_40_since`` on the same row
  (``docs/DATABASE.md`` §17.3);
- **expiry is proven by data, never by a clock.** Fifteen minutes below the floor
  need both the elapsed time *and* the readings that cover it — sixteen points
  span fifteen intervals — and any sample that is not eligible **zeroes** the run
  rather than pausing it. Four minutes below, ten minutes blind and one more
  below is not fifteen proven minutes (the doctrine of ``anomalies/lifecycle.py``,
  and Astra, T2.4 design review, item 8). The pure function cannot see a gap it
  was never told about: the watchdog must feed an ineligible sample for the
  minutes nothing arrived;
- **an eligible anomaly at or above the ANOMALY threshold sustains the episode.**
  Without it, a market scoring 30 with a live severity-70 anomaly expires while
  the anomaly is still firing, and reopens as a "new" opportunity for the same
  unchanged condition. This is a **revision of the literal contract** (which only
  says "below 40 for fifteen minutes"), taken with Astra (item 7) and recorded in
  ``.claude/state/notes-T2.4.md``;
- **above ``NORMAL`` needs a score above the watching line, or an anomaly.** That
  is what keeps ``EXTENDED`` — a *stage*, which a market can wear at any score —
  from opening an episode on a market nobody is watching, and closes the same
  ambiguity for every other status that precedes ``WATCHING``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from hunter_core.domain.enums import OpportunityStage, OpportunityStatus
from hunter_indicators.opportunity.episode import (
    REASON_BELOW_FLOOR_PROVEN,
    REASON_EPISODE_CLOSED,
    REASON_NOT_ELIGIBLE,
    REASON_STALE_OBSERVATION,
    REASON_SUSTAINED_BY_ANOMALY,
    EpisodeAction,
    EpisodeState,
    StatusDecision,
    StatusSample,
    StatusThresholds,
)


def candidate_status(sample: StatusSample, thresholds: StatusThresholds) -> OpportunityStatus:
    """The status this sample argues for, before the episode's own history."""
    if sample.score is None:
        return OpportunityStatus.NORMAL
    watched = sample.score >= thresholds.watching_min
    anomalous = (
        sample.anomaly_severity is not None
        and sample.anomaly_severity >= thresholds.anomaly_severity_min
    )
    if watched and sample.stage is OpportunityStage.EXTENDED:
        return OpportunityStatus.EXTENDED
    if sample.score >= thresholds.entry_candidate_min and sample.agreeing_signals > 0:
        return OpportunityStatus.ENTRY_CANDIDATE
    if sample.score >= thresholds.hot_min:
        return OpportunityStatus.HOT
    if anomalous:
        return OpportunityStatus.ANOMALY
    if watched:
        return OpportunityStatus.WATCHING
    return OpportunityStatus.NORMAL


def _floor_run(
    state: EpisodeState | None,
    sample: StatusSample,
    thresholds: StatusThresholds,
) -> tuple[datetime | None, int, str | None]:
    """The below-the-floor run after this sample: ``(since, readings, reason)``."""
    if not sample.usable:
        return None, 0, REASON_NOT_ELIGIBLE
    if (
        sample.anomaly_severity is not None
        and sample.anomaly_severity >= thresholds.anomaly_severity_min
    ):
        return None, 0, REASON_SUSTAINED_BY_ANOMALY
    assert sample.score is not None
    if sample.score >= thresholds.score_floor:
        return None, 0, None
    since = state.below_floor_since if state is not None else None
    readings = state.below_floor_readings if state is not None else 0
    if since is None:
        return sample.observation_ts, 1, None
    return since, readings + 1, None


def _proven(
    since: datetime | None, readings: int, sample: StatusSample, thresholds: StatusThresholds
) -> bool:
    return (
        since is not None
        and sample.observation_ts - since >= thresholds.below_floor_window
        and readings >= thresholds.below_floor_min_readings
    )


def advance_status(
    state: EpisodeState | None,
    sample: StatusSample,
    thresholds: StatusThresholds,
) -> StatusDecision:
    """``state`` plus one sample: the status now, and what the caller must write."""
    candidate = candidate_status(sample, thresholds)
    if state is not None and not state.open:
        return StatusDecision(
            action=EpisodeAction.NONE,
            status=state.status,
            candidate=candidate,
            state_in=state,
            state_out=state,
            thresholds_version=thresholds.weights_version,
            reason=REASON_EPISODE_CLOSED,
        )
    if state is not None and sample.observation_ts <= state.observation_ts:
        return StatusDecision(
            action=EpisodeAction.NONE,
            status=state.status,
            candidate=candidate,
            state_in=state,
            state_out=state,
            thresholds_version=thresholds.weights_version,
            reason=REASON_STALE_OBSERVATION,
        )

    since, readings, run_reason = _floor_run(state, sample, thresholds)

    if state is None:
        if candidate is OpportunityStatus.NORMAL or not sample.usable:
            return StatusDecision(
                action=EpisodeAction.NONE,
                status=OpportunityStatus.NORMAL,
                candidate=candidate,
                state_in=None,
                state_out=None,
                thresholds_version=thresholds.weights_version,
                reason=None if sample.usable else REASON_NOT_ELIGIBLE,
            )
        assert sample.score is not None
        opened = EpisodeState(
            status=candidate,
            first_seen_at=sample.observation_ts,
            observation_ts=sample.observation_ts,
            score=sample.score,
            peak_score=sample.score,
            stage=sample.stage,
            direction=sample.direction,
            confidence=sample.confidence,
            below_floor_since=since,
            below_floor_readings=readings,
        )
        return StatusDecision(
            action=EpisodeAction.OPEN,
            status=candidate,
            candidate=candidate,
            state_in=None,
            state_out=opened,
            thresholds_version=thresholds.weights_version,
            reason=run_reason,
        )

    if not sample.usable:
        held = replace(
            state,
            observation_ts=sample.observation_ts,
            below_floor_since=None,
            below_floor_readings=0,
        )
        return StatusDecision(
            action=EpisodeAction.HOLD,
            status=state.status,
            candidate=candidate,
            state_in=state,
            state_out=held,
            thresholds_version=thresholds.weights_version,
            reason=REASON_NOT_ELIGIBLE,
        )

    assert sample.score is not None
    if _proven(since, readings, sample, thresholds):
        expired = replace(
            state,
            status=OpportunityStatus.EXPIRED,
            observation_ts=sample.observation_ts,
            score=sample.score,
            peak_score=max(state.peak_score, sample.score),
            stage=sample.stage,
            direction=sample.direction,
            confidence=sample.confidence,
            below_floor_since=since,
            below_floor_readings=readings,
            expired_at=sample.observation_ts,
        )
        return StatusDecision(
            action=EpisodeAction.EXPIRE,
            status=OpportunityStatus.EXPIRED,
            candidate=candidate,
            state_in=state,
            state_out=expired,
            thresholds_version=thresholds.weights_version,
            reason=REASON_BELOW_FLOOR_PROVEN,
        )

    updated = replace(
        state,
        status=candidate,
        observation_ts=sample.observation_ts,
        score=sample.score,
        peak_score=max(state.peak_score, sample.score),
        stage=sample.stage,
        direction=sample.direction,
        confidence=sample.confidence,
        below_floor_since=since,
        below_floor_readings=readings,
    )
    return StatusDecision(
        action=EpisodeAction.UPDATE,
        status=candidate,
        candidate=candidate,
        state_in=state,
        state_out=updated,
        thresholds_version=thresholds.weights_version,
        reason=run_reason,
    )


__all__ = ["advance_status", "candidate_status"]
