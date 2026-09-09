"""Turning a :class:`~hunter_core.strategies.base.Decision` into the rows and the
event that will be written for it — SHADOW-LAB.md §2, §3 and §6.

Nothing here touches the database or Redis. It builds, from the strategy's pure
output plus what only the *run* knows (``decision_at``, the cohort, the chosen
entry bar, what data had actually arrived), the four immutable artefacts of one
shadow decision:

- ``agent_signals.supporting_features`` — S1's envelope, plus the run's labels
  and provenance. Written once and never rewritten;
- the frozen levels, already at the database's scale (:mod:`.levels`), so the
  number the outcome uses after a restart is the number that was stored;
- ``signal_outcomes.meta`` — the entry plan, the cost hypothesis, the walker's
  starting progress and everything needed to rebuild the tracking plan without
  re-reading the strategy code;
- the ``shadow.signals.emitted`` payload, carrying the emitting version's own
  ``purpose`` (T3.15, D10: ``research_only`` or ``paper`` — never ``live``,
  which :mod:`hunter_strategy_worker.catalogue` refuses before a version this
  old even reaches :func:`build_record`) so a consumer can decide by name.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_core.domain.enums import ShadowTrackingState
from hunter_core.strategies.canonical import canonical_json
from hunter_core.strategies.envelope import AssumedCosts
from hunter_strategy_worker.levels import to_db_scale, to_db_scale_all
from hunter_strategy_worker.plan import EntryPlan
from hunter_strategy_worker.walker import Progress, TrackingPlan

if TYPE_CHECKING:
    from hunter_core.strategies.base import Decision
    from hunter_strategy_worker.catalogue import ActiveVersion
    from hunter_strategy_worker.regime_gate import RegimeGate
    from hunter_strategy_worker.repo import MarketRow

__all__ = ["Provenance", "ShadowRecord", "build_record"]


def _jsonable(value: object) -> Any:
    """Canonical JSON shape: decimals as normalised strings, timestamps as ``Z``."""
    return json.loads(canonical_json(value))


@dataclass(frozen=True, slots=True)
class Provenance:
    """What was actually available when the decision was taken.

    The cut at ``source_bar_close`` controls market time, not availability: a
    candle backfilled *after* the decision still passes it. Reproducing a past
    decision needs this (notes-S1.md §12).
    """

    available_through: datetime | None
    """Newest ``candles.received_at`` behind the context."""
    newest_bar_open: datetime | None
    """Newest 1m ``open_time`` in the context."""
    bars_in_context: int
    eligibility_observed_at: datetime
    """When ``markets.is_monitored`` was read — universe membership is
    overwritten in place, so the reading is only evidence near its own instant."""
    producer: str
    code_ref: str | None
    funding_ts: datetime | None
    """``ts`` of the funding observation the context received, if any."""
    funding_source: str | None
    """``"durable"`` or ``"hot_state"``; ``None`` when ``funding_ts`` is ``None``."""
    funding_reason: str | None
    """Why there is no funding observation; ``None`` when ``funding_ts`` is set
    (:mod:`hunter_strategy_worker.derivatives`)."""
    open_interest_ts: datetime | None
    open_interest_source: str | None
    open_interest_reason: str | None
    """``regime_id``/``regime_reason`` are deliberately *not* here: the regime
    lookup happens later, under the slot lock in ``decide.py`` (closer to the
    actual write), and reaches the envelope as :func:`build_record`'s own
    keyword arguments instead."""

    regime_gate: RegimeGate | None = None
    """The hourly-regime verdict that let this decision happen (T3.52), or
    ``None`` when the version carries no ``eligibility_policy``. Unlike
    ``regime_id`` above it *is* part of the provenance of the context: the gate
    is evaluated while the context is built, because it decides
    ``StrategyContext.eligible``.

    A **refusal** never reaches here — there is no signal, so there is no
    envelope; it lives in the ``Evaluation`` (state ``ineligible``, detail
    ``eligibility_reason = regime_gate:<label>``), which is what the evaluation
    log and the replay ledger record. What is written here is the other half:
    which row, which hour and which label allowed the decision, so the ledger can
    be decomposed by regime without re-deriving the join.
    """

    context_minutes: int = 0
    """How much 1m history this evaluation actually loaded (T3.54b).

    A property of the *version* since T3.54b — derived from its own frozen
    parameters and clamped by the two operational knobs — so it belongs in the
    provenance next to ``bars_in_context``: that one says how many candles were
    there, this one says how many were **asked for**. The pair separates a
    market with a hole from a version reading a window shorter than its longest
    lookback, which is the difference T3.54 could only establish by reading the
    deployment's environment (notes-T3.54 §6.5).

    ``0`` is the never-set default and exists only so the dataclass can grow a
    field behind ``regime_gate``; the one place that builds a ``Provenance``
    (:mod:`hunter_strategy_worker.context`) always passes the real number.
    """


@dataclass(frozen=True, slots=True)
class ShadowRecord:
    """Everything one decision writes, already in its persisted shape."""

    signal_id: uuid.UUID
    strategy_version_id: uuid.UUID
    market_id: uuid.UUID
    params_hash: str
    cohort: str
    decision_at: datetime
    source_bar_close: datetime
    stop: Decimal
    target1: Decimal
    targets: tuple[Decimal, ...]
    reference_price: Decimal
    horizon_s: int
    confidence: Decimal
    reason: str
    invalidations: list[dict[str, Any]]
    supporting_features: dict[str, Any]
    meta: dict[str, Any]
    payload: dict[str, Any]
    tracking_state: ShadowTrackingState
    no_entry_reason: str | None
    plan: EntryPlan
    regime_id: uuid.UUID | None

    @property
    def entered_slot(self) -> bool:
        """Whether this decision leaves the slot holding an open tracking.

        A decision already born ``no_entry`` (late) never occupies the slot: it
        would hold the market's candles for a tracking nobody is following
        (Astra, S2 design review, must-fix 1).
        """
        return self.tracking_state is ShadowTrackingState.PENDING_ENTRY


def _tracking_plan(decision: Decision, costs: AssumedCosts, plan: EntryPlan) -> TrackingPlan:
    invalidation = decision.invalidations[0] if decision.invalidations else None
    from hunter_core.domain.enums import Timeframe

    return TrackingPlan(
        entry_bar_open=plan.entry_bar_open,
        stop=to_db_scale(decision.stop),
        target1=to_db_scale(decision.target1),
        horizon_s=decision.horizon_s,
        costs=costs,
        reference_price=to_db_scale(decision.reference_price),
        invalidation_level=None if invalidation is None else to_db_scale(invalidation.level),
        invalidation_timeframe=None if invalidation is None else Timeframe(invalidation.timeframe),
    )


def build_record(
    *,
    signal_id: uuid.UUID,
    version: ActiveVersion,
    market: MarketRow,
    decision: Decision,
    costs: AssumedCosts,
    decision_at: datetime,
    cohort: str,
    plan: EntryPlan,
    provenance: Provenance,
    regime_id: uuid.UUID | None = None,
    regime_reason: str | None = None,
) -> ShadowRecord:
    """Assemble the immutable artefacts of one shadow decision.

    ``regime_id``/``regime_reason`` are separate from ``provenance`` because the
    regime lookup happens later, under the slot lock in ``decide.py``, not while
    the context was built — but both land in the same envelope
    ``provenance`` block (SHADOW-LAB.md §2: written once, at the decision).
    """
    tracking = _tracking_plan(decision, costs, plan)
    targets = to_db_scale_all((decision.target1, *decision.targets_informational))
    envelope = decision.supporting_features.to_jsonable()
    envelope["decision_at"] = _jsonable(decision_at)
    envelope["cohort"] = cohort
    # T3.15/D10: the label is the *version's*, not the strategy's. A strategy
    # builds its envelope with ``SignalEnvelope``'s default (``research_only``)
    # because the code has no idea which coorte it is running for; the row that
    # activated it does, and this is the one place that label is stamped.
    envelope["purpose"] = version.purpose
    envelope["provenance"] = _jsonable(
        {
            "available_through": provenance.available_through,
            "newest_bar_open": provenance.newest_bar_open,
            "bars_in_context": provenance.bars_in_context,
            "context_minutes": provenance.context_minutes,
            "eligibility_observed_at": provenance.eligibility_observed_at,
            "producer": provenance.producer,
            "code_ref": provenance.code_ref,
            "strategy_version_id": version.id,
            "params_hash": version.params_hash,
            "funding_ts": provenance.funding_ts,
            "funding_source": provenance.funding_source,
            "funding_reason": provenance.funding_reason,
            "open_interest_ts": provenance.open_interest_ts,
            "open_interest_source": provenance.open_interest_source,
            "open_interest_reason": provenance.open_interest_reason,
            "regime_id": regime_id,
            "regime_reason": regime_reason,
            "regime_gate": (
                None if provenance.regime_gate is None else provenance.regime_gate.to_jsonable()
            ),
        }
    )
    late = plan.late_reason
    state = ShadowTrackingState.NO_ENTRY if late else ShadowTrackingState.PENDING_ENTRY
    progress = Progress.start()
    if late:
        progress = Progress(
            tracking_state=ShadowTrackingState.NO_ENTRY,
            result=progress.result,
            no_entry_reason=late.value,
        )
    meta = _jsonable(
        {
            "entry_plan": plan.to_jsonable(),
            "assumed_costs": costs.model_dump(),
            "cohort": cohort,
            "purpose": version.purpose,
            "horizon_s": decision.horizon_s,
            "reference_price": tracking.reference_price,
            "invalidation": (
                None
                if tracking.invalidation_level is None
                else {
                    "level": tracking.invalidation_level,
                    "timeframe": (
                        tracking.invalidation_timeframe.value
                        if tracking.invalidation_timeframe
                        else None
                    ),
                    "kind": "close_below",
                }
            ),
            "progress": progress.to_jsonable(),
            "excursions": progress.excursions(tracking),
            "funding": None,
        }
    )
    payload = _jsonable(
        {
            "signal_id": signal_id,
            "strategy_version_id": version.id,
            "strategy": version.strategy_key,
            "version": version.version,
            "market_id": market.id,
            "exchange": market.exchange,
            "symbol": market.symbol,
            "cohort": cohort,
            "purpose": version.purpose,
            "params_hash": version.params_hash,
            "source_bar_close": decision.supporting_features.observation_ts,
            "decision_at": decision_at,
            "direction": decision.direction.value,
            "reference_price": tracking.reference_price,
            "stop": tracking.stop,
            "target1": tracking.target1,
            "horizon_s": decision.horizon_s,
            "entry_bar_open": plan.entry_bar_open,
            "tracking_state": state.value,
            "no_entry_reason": late.value if late else None,
        }
    )
    return ShadowRecord(
        signal_id=signal_id,
        strategy_version_id=version.id,
        market_id=market.id,
        params_hash=version.params_hash,
        cohort=cohort,
        decision_at=decision_at,
        source_bar_close=decision.supporting_features.observation_ts,
        stop=tracking.stop,
        target1=tracking.target1,
        targets=targets,
        reference_price=to_db_scale(decision.reference_price),
        horizon_s=decision.horizon_s,
        confidence=decision.confidence,
        reason=decision.reason,
        invalidations=_jsonable([i.model_dump() for i in decision.invalidations]),
        supporting_features=envelope,
        meta=meta,
        payload=payload,
        tracking_state=state,
        no_entry_reason=late.value if late else None,
        plan=plan,
        regime_id=regime_id,
    )
