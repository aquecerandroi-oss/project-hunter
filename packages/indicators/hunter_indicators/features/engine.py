"""The feature engine: context + carried state -> one :class:`FeatureVector`.

Order matters and is fixed:

1. the anchored ATR checkpoint is advanced **once** with the bars the context
   closed (``atr.advance_from_context``), and the resulting state is what the
   calculators read — so every feature in a vector sees the same volatility;
2. the provenance of every input is computed once from the freshness policy;
3. each calculator produces its own value, then **inherits** the quality of the
   inputs it declared: an input that is degraded degrades the features that used
   it, and nothing else. There is no vector-wide gate (Astra, T2.2 design
   review, 2c): a warming-up funding history must not hide a perfectly good
   return.

The function is pure: no clock, no IO, no Redis. ``ctx.as_of`` is the only
notion of "now", which is what lets a bootstrap over persisted candles and the
live scanner produce the same bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hunter_indicators.features.atr import advance_from_context
from hunter_indicators.features.context import MarketContext
from hunter_indicators.features.definitions import FeatureCalculator, FeatureRegistry
from hunter_indicators.features.deriv import deriv_calculators
from hunter_indicators.features.micro import micro_calculators
from hunter_indicators.features.price import price_calculators
from hunter_indicators.features.quality import FreshnessPolicy, provenance_for
from hunter_indicators.features.state import EMPTY_STATE, FeatureState
from hunter_indicators.features.trend import trend_calculators
from hunter_indicators.features.vector import (
    FeatureValue,
    FeatureVector,
    InputProvenance,
    Quality,
    Reason,
)
from hunter_indicators.features.volume import volume_calculators


def default_calculators() -> tuple[FeatureCalculator, ...]:
    """The frozen v1 roster, ordered by key."""
    calculators: list[FeatureCalculator] = [
        *price_calculators(),
        *volume_calculators(),
        *micro_calculators(),
        *deriv_calculators(),
        *trend_calculators(),
    ]
    ordered = sorted(calculators, key=lambda c: c.definition.key)
    return tuple(ordered)


DEFAULT_REGISTRY = FeatureRegistry(default_calculators())
"""Feature set v1. Adding, removing or re-versioning a feature moves
``feature_set_version``, which is exactly the point: a snapshot says which set
produced it."""


def default_definitions_rows(
    registry: FeatureRegistry = DEFAULT_REGISTRY,
) -> list[dict[str, Any]]:
    """The ``feature_definitions`` rows of ``registry``, ordered by key.

    The single public door for seeding and upserting the catalogue (T2.1's seed,
    T2.5's startup): the table must describe *this* engine, with this build's
    ``inputs`` vocabulary, versions and parameters, or a stored snapshot points
    at a definition that never produced it. Each call returns fresh dicts, so a
    caller that adapts a row for its driver cannot mutate the next one's.
    """
    return [definition.as_row() for definition in registry.definitions()]


@dataclass(frozen=True, slots=True)
class FeatureResult:
    """The vector and the state to carry into the next computation."""

    vector: FeatureVector
    state: FeatureState


def _inherit(value: FeatureValue, provenance: dict[str, InputProvenance]) -> FeatureValue:
    """Downgrade ``value`` to the worst quality among the inputs it used."""
    for name in value.inputs:
        entry = provenance.get(name)
        if entry is None or entry.quality is Quality.OK:
            continue
        if entry.quality is Quality.UNAVAILABLE:
            value = value.degraded_to(Quality.UNAVAILABLE, entry.reason or Reason.MISSING_INPUT)
        else:
            value = value.degraded_to(Quality.DEGRADED, entry.reason or Reason.STALE_INPUT)
    return value


def compute_features(
    ctx: MarketContext,
    state: FeatureState = EMPTY_STATE,
    *,
    registry: FeatureRegistry = DEFAULT_REGISTRY,
    policy: FreshnessPolicy | None = None,
) -> FeatureResult:
    """Every registered feature of ``ctx``, plus the state to carry forward."""
    policy = policy or FreshnessPolicy()
    advanced = advance_from_context(ctx, state.atr_15m)
    next_state = FeatureState(atr_15m=advanced.checkpoint)
    provenance = provenance_for(ctx, policy, advanced)
    values: dict[str, FeatureValue] = {}
    for calculator in registry.all():
        value = calculator.compute(ctx, next_state)
        values[calculator.definition.key] = _inherit(value, provenance)
    vector = FeatureVector(
        exchange=ctx.exchange,
        symbol=ctx.symbol,
        ts=ctx.as_of,
        feature_set_version=registry.feature_set_version,
        values=values,
        provenance=provenance,
        quality_policy_version=policy.identity,
    )
    return FeatureResult(vector=vector, state=next_state)


__all__ = [
    "DEFAULT_REGISTRY",
    "FeatureResult",
    "compute_features",
    "default_calculators",
    "default_definitions_rows",
]
