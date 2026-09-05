"""Strategy framework — the Shadow Lab's pure decision layer.

Two halves of one contract:

- **durable** (S0): :mod:`hunter_core.strategies.canonical`, the
  ``params_format = 1`` serialisation every frozen strategy version, every
  ``params_hash`` and every deterministic signal id is derived from;
- **pure** (S1): the :class:`Strategy` protocol, the :class:`StrategyContext`
  cut at ``source_bar_close``, the :class:`Decision` with its immutable
  envelope, 1m -> 5m/15m aggregation, the Wilder ATR, and the v1 strategies
  ``momentum_v1`` and ``volume_anomaly_v1``.

Nothing here does IO or reads a clock: ``Strategy.evaluate(ctx, params)`` is a
function of the context alone (docs/ARCHITECTURE.md §6). Design decisions and the
one divergence from the M2 calculator are written down in
``.claude/state/notes-S1.md``.
"""

from __future__ import annotations

from hunter_core.strategies.aggregate import Bar, Window, aggregate
from hunter_core.strategies.base import (
    PURPOSE_RESEARCH_ONLY,
    Decision,
    Evaluation,
    EvaluationState,
    Invalidation,
    Strategy,
    StrategyContext,
    build_context,
    param_decimal,
    param_int,
)
from hunter_core.strategies.canonical import PARAMS_FORMAT, canonical_json, params_hash
from hunter_core.strategies.envelope import (
    AssumedCosts,
    AtrEvidence,
    FeatureEvidence,
    SupportingFeatures,
)
from hunter_core.strategies.indicators import ATR_METHOD, ATR_ORIGIN, Atr, wilder_atr
from hunter_core.strategies.momentum_v1 import MOMENTUM_V1, MomentumV1
from hunter_core.strategies.numeric import CONTEXT
from hunter_core.strategies.registry import DEFAULT_REGISTRY, StrategyRegistry
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1, VolumeAnomalyV1

__all__ = [
    "ATR_METHOD",
    "ATR_ORIGIN",
    "CONTEXT",
    "DEFAULT_REGISTRY",
    "MOMENTUM_V1",
    "PARAMS_FORMAT",
    "PURPOSE_RESEARCH_ONLY",
    "VOLUME_ANOMALY_V1",
    "AssumedCosts",
    "Atr",
    "AtrEvidence",
    "Bar",
    "Decision",
    "Evaluation",
    "EvaluationState",
    "FeatureEvidence",
    "Invalidation",
    "MomentumV1",
    "Strategy",
    "StrategyContext",
    "StrategyRegistry",
    "SupportingFeatures",
    "VolumeAnomalyV1",
    "Window",
    "aggregate",
    "build_context",
    "canonical_json",
    "param_decimal",
    "param_int",
    "params_hash",
    "wilder_atr",
]
