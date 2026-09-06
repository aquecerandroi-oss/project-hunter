"""The classification itself: candidate, precedence, hysteresis, invalidation.

Four rules, each with a reason:

- **EARLY needs all four confirmations** (``relative_volume_1h >= 3``,
  ``trade_velocity_1m >= 2x`` its baseline, ``open_interest_change_1h >= +2%``,
  order flow aligned). The joint decision spells them with "and"; "an
  unavailable feature does not confirm" removes a confirmation, not the
  requirement, so a market whose tape is missing is ``NONE``, never EARLY;
- **direction is the sign of ``return_1h``** and a flat return confirms nothing —
  there is no side for the order-flow test to align with;
- **precedence EXTENDED > DEVELOPING > EARLY > none** applies to the *candidate*,
  before the hysteresis;
- **the published stage changes only after two distinct, strictly increasing
  observations** with the same candidate *and the same side* — and it is
  **withdrawn** after the same number of observations that fail to support it,
  because taking a claim down and putting a new one up are different decisions
  (Astra, revisão do fix-pass) — but a **loss of quality in anything
  the published stage rests on invalidates it immediately**. Waiting for
  confirmation to *stop* claiming something is backwards: the confirmation
  protects against flapping, not against blindness.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, localcontext

from hunter_core.domain.enums import OpportunityStage, TradeDirection
from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.features.vector import FeatureValue, FeatureVector, Quality, Reason
from hunter_indicators.stage.model import (
    ATR_KEY,
    CONFIRMATION_KEYS,
    EMPTY_STAGE_STATE,
    NO_STAGE_EXTRAS,
    READ_KEYS,
    REASON_ATR_DEGRADED,
    REASON_ATR_WARMUP,
    REASON_NOT_CONFIRMED,
    REASON_QUALITY_LOST,
    REASON_RETURN_UNAVAILABLE,
    REASON_STAGE_WITHDRAWN,
    REASON_STALE_OBSERVATION,
    RETURN_4H_KEY,
    RETURN_KEY,
    STAGE_BASIS_EXHAUSTION,
    STAGE_BASIS_RATIO,
    StageDecision,
    StageInputs,
    StageState,
    StageThresholds,
)

_ATR_WARMUP_REASONS = frozenset(
    {Reason.WARMUP, Reason.INSUFFICIENT_SAMPLE, Reason.INSUFFICIENT_COVERAGE}
)
"""Why an ATR is *not there yet*, as opposed to being there and unbelievable."""


def _atr_reason(value: FeatureValue | None) -> str:
    """``atr_warmup`` when there is no ATR yet, ``atr_degraded`` when the reading
    cannot be believed. Both stop the classification, but they send an operator
    to different places: one is a market we have not watched long enough, the
    other is our own collection failing (cross review, nice-to-have e)."""
    if value is None:
        return REASON_ATR_WARMUP  # the vector does not carry the feature at all
    if value.quality is Quality.OK:
        return REASON_ATR_WARMUP  # a zero ATR: no scale established yet
    if value.quality is Quality.UNAVAILABLE and value.reason in _ATR_WARMUP_REASONS:
        return REASON_ATR_WARMUP
    return REASON_ATR_DEGRADED


def _ok_value(vector: FeatureVector, key: str) -> Decimal | None:
    """The reading of ``key`` only when ``ok`` — degraded never classifies."""
    value = vector.values.get(key)
    if value is None or value.quality is not Quality.OK:
        return None
    return value.value


def _lost(
    state: StageState,
    values: Mapping[str, Decimal | None],
    inputs: StageInputs,
    thresholds: StageThresholds,
) -> list[str]:
    """Everything the **published** stage rests on that is no longer readable.

    Features *and* the external evidence of :class:`StageInputs`: a published
    EARLY whose ``trade_velocity`` baseline disappeared is resting on a
    confirmation nobody can check any more, and waiting for the hysteresis to
    take it down would keep claiming it (Astra, T2.3 diff review, must-fix 5).
    """
    if state.stage is OpportunityStage.NONE:
        return []
    keys = [RETURN_KEY, ATR_KEY]
    external: list[str] = []
    if state.stage is OpportunityStage.EARLY:
        keys += list(CONFIRMATION_KEYS)
        if inputs.trade_velocity_baseline is None:
            external.append("trade_velocity_baseline")
    elif state.stage is OpportunityStage.EXTENDED and state.basis == STAGE_BASIS_EXHAUSTION:
        keys.append(RETURN_4H_KEY)
        if len(inputs.relative_volume_15m_closes) < thresholds.extended_relative_volume_15m_closes:
            external.append("relative_volume_15m_closes")
    return [key for key in keys if values[key] is None] + external


def _confirmations(
    vector: FeatureVector,
    thresholds: StageThresholds,
    inputs: StageInputs,
    direction: TradeDirection,
) -> dict[str, bool]:
    """The four symmetric confirmations. An absent feature never confirms."""
    relative_volume, velocity, oi_change, pressure = (
        _ok_value(vector, key) for key in CONFIRMATION_KEYS
    )
    baseline = inputs.trade_velocity_baseline
    with localcontext(CONTEXT):
        if direction is TradeDirection.LONG:
            pressure_ok = pressure is not None and pressure >= thresholds.buy_pressure_5m_long_min
        elif direction is TradeDirection.SHORT:
            pressure_ok = pressure is not None and pressure <= thresholds.buy_pressure_5m_short_max
        else:
            pressure_ok = False
        return {
            "relative_volume_1h": relative_volume is not None
            and relative_volume >= thresholds.relative_volume_1h_min,
            "trade_velocity_1m": velocity is not None
            and baseline is not None
            and baseline > 0
            and velocity >= thresholds.trade_velocity_baseline_multiple_min * baseline,
            "open_interest_change_1h": oi_change is not None
            and oi_change >= thresholds.open_interest_change_1h_min,
            "buy_pressure_5m": pressure_ok,
        }


def _exhausted(
    vector: FeatureVector, thresholds: StageThresholds, inputs: StageInputs, atr: Decimal
) -> bool:
    """The alternative EXTENDED: a long run plus a fading 15-minute volume."""
    return_4h = _ok_value(vector, RETURN_4H_KEY)
    if return_4h is None:
        return False
    with localcontext(CONTEXT):
        if abs(return_4h) <= thresholds.extended_return_4h_atr_multiple * atr:
            return False
    closes: Sequence[Decimal] = inputs.relative_volume_15m_closes
    over = thresholds.extended_relative_volume_15m_closes
    if len(closes) < over:
        return False
    window = list(closes[-over:])
    falls = sum(1 for index in range(1, over) if window[index] < window[index - 1])
    return falls >= thresholds.extended_relative_volume_15m_declines


def _publish(
    state: StageState,
    candidate: OpportunityStage,
    basis: str,
    observation_ts: datetime,
    thresholds: StageThresholds,
    direction: TradeDirection,
) -> StageState:
    """The hysteresis over the **pair** ``(stage, direction)``.

    A change needs ``confirmations`` distinct observations, and a sign inversion
    *is* a change: "EARLY long" and "EARLY short" are different claims about the
    market, so republishing the second one takes the same two observations as
    moving from EARLY to DEVELOPING. The side of what is published therefore
    never comes from the observation being evaluated.
    """
    side = direction if candidate is not OpportunityStage.NONE else TradeDirection.NEUTRAL
    if candidate is state.stage and side is state.direction:
        return StageState(
            stage=state.stage,
            basis=basis or state.basis,
            candidate=candidate,
            confirmations=0,
            last_observation_ts=observation_ts,
            direction=state.direction,
            candidate_direction=side,
            unsupported=0,
        )
    same_candidate = candidate is state.candidate and side is state.candidate_direction
    count = state.confirmations + 1 if same_candidate else 1
    if count >= thresholds.confirmations:
        return StageState(
            stage=candidate,
            basis=basis,
            candidate=candidate,
            confirmations=0,
            last_observation_ts=observation_ts,
            direction=side,
            candidate_direction=side,
            unsupported=0,
        )
    unsupported = state.unsupported + 1
    if state.stage is not OpportunityStage.NONE and unsupported >= thresholds.confirmations:
        # nothing has confirmed a replacement, but what is published has not been
        # supported for ``confirmations`` observations: stop claiming it
        return StageState(
            stage=OpportunityStage.NONE,
            basis="",
            candidate=candidate,
            confirmations=count,
            last_observation_ts=observation_ts,
            direction=TradeDirection.NEUTRAL,
            candidate_direction=side,
            unsupported=0,
        )
    return StageState(
        stage=state.stage,
        basis=state.basis,
        candidate=candidate,
        confirmations=count,
        last_observation_ts=observation_ts,
        direction=state.direction,
        candidate_direction=side,
        unsupported=unsupported,
    )


def _candidate_of(
    vector: FeatureVector,
    thresholds: StageThresholds,
    inputs: StageInputs,
    ratio: Decimal,
    atr: Decimal,
    confirmations: Mapping[str, bool],
) -> tuple[OpportunityStage, str, str | None]:
    """Precedence EXTENDED > DEVELOPING > EARLY > none, before the hysteresis."""
    if ratio > thresholds.r_developing_max:
        return OpportunityStage.EXTENDED, STAGE_BASIS_RATIO, None
    if _exhausted(vector, thresholds, inputs, atr):
        return OpportunityStage.EXTENDED, STAGE_BASIS_EXHAUSTION, None
    if ratio >= thresholds.r_early_max:
        return OpportunityStage.DEVELOPING, STAGE_BASIS_RATIO, None
    if all(confirmations.values()):
        return OpportunityStage.EARLY, STAGE_BASIS_RATIO, None
    return OpportunityStage.NONE, "", REASON_NOT_CONFIRMED


def classify_stage(
    vector: FeatureVector,
    *,
    thresholds: StageThresholds,
    state: StageState = EMPTY_STAGE_STATE,
    inputs: StageInputs = NO_STAGE_EXTRAS,
    observation_ts: datetime | None = None,
) -> StageDecision:
    """The stage of one market at one instant, plus the state to carry forward.

    ``observation_ts`` is the **identity of the observation**, not the instant of
    processing. It defaults to the minute of ``vector.ts`` because the vector
    carries ``ctx.as_of``: recomputing 14:03 a second later is the same
    observation, and counting it twice would fabricate a confirmation the market
    never gave (Astra, T2.3 diff review, must-fix 4).
    """
    observation_ts = ensure_utc(
        observation_ts if observation_ts is not None else vector.ts.replace(second=0, microsecond=0)
    )
    version = thresholds.weights_version
    if state.last_observation_ts is not None and observation_ts <= state.last_observation_ts:
        # a duplicate or an out-of-order evaluation confirms nothing
        return StageDecision(
            stage=state.stage,
            candidate=state.candidate,
            basis=state.basis,
            observation_ts=observation_ts,
            state_in=state,
            state_out=state,
            thresholds_version=version,
            reason=REASON_STALE_OBSERVATION,
        )

    values: Mapping[str, Decimal | None] = {key: _ok_value(vector, key) for key in READ_KEYS}
    atr = values[ATR_KEY]
    return_1h = values[RETURN_KEY]
    if atr is None or atr <= 0 or return_1h is None:
        return StageDecision(
            stage=OpportunityStage.NONE,
            candidate=OpportunityStage.NONE,
            observation_ts=observation_ts,
            state_in=state,
            state_out=StageState(last_observation_ts=observation_ts),
            thresholds_version=version,
            reason=(
                _atr_reason(vector.values.get(ATR_KEY))
                if atr is None or atr <= 0
                else REASON_RETURN_UNAVAILABLE
            ),
            invalidated=state.stage is not OpportunityStage.NONE,
            values=values,
            inputs=inputs,
        )

    with localcontext(CONTEXT):
        ratio = abs(return_1h) / atr
    direction = TradeDirection.NEUTRAL  # a flat return has no side to align with
    if return_1h != 0:
        direction = TradeDirection.LONG if return_1h > 0 else TradeDirection.SHORT
    confirmations = _confirmations(vector, thresholds, inputs, direction)
    candidate, basis, reason = _candidate_of(vector, thresholds, inputs, ratio, atr, confirmations)

    lost = _lost(state, values, inputs, thresholds)
    if lost:
        # the published stage rests on something we can no longer see: drop it now
        state_out = StageState(
            candidate=candidate,
            last_observation_ts=observation_ts,
            candidate_direction=(
                direction if candidate is not OpportunityStage.NONE else TradeDirection.NEUTRAL
            ),
        )
        reason, basis = REASON_QUALITY_LOST, ""
    else:
        state_out = _publish(state, candidate, basis, observation_ts, thresholds, direction)
        if state_out.stage is not OpportunityStage.NONE:
            basis = state_out.basis
        elif state.stage is not OpportunityStage.NONE:
            reason, basis = REASON_STAGE_WITHDRAWN, ""
    return StageDecision(
        stage=state_out.stage,
        candidate=candidate,
        basis=basis,
        direction=direction,
        observation_ts=observation_ts,
        state_in=state,
        state_out=state_out,
        thresholds_version=version,
        r=ratio,
        reason=reason,
        invalidated=bool(lost),
        confirmations=confirmations,
        values=values,
        inputs=inputs,
    )


__all__ = ["classify_stage"]
