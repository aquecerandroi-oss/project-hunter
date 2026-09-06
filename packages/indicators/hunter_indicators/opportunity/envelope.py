"""The sample envelope: everything a stored score needs to be recomputed.

Split from ``scorer.py`` for the 350-line budget
(``infra/scripts/check_file_size.py``). ``scorer.py`` decides the number; this
module writes down what the number was decided from —
``opportunities.feature_snapshot`` and ``opportunity_history.envelope``
(``docs/DATABASE.md`` §17.3).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from hunter_core.strategies.canonical import canonical_json
from hunter_indicators.opportunity.model import ScoreResult
from hunter_indicators.opportunity.scorer import ScoreContext


def opportunity_envelope(
    result: ScoreResult,
    ctx: ScoreContext,
    *,
    regime_id: UUID | None = None,
    status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The full sample envelope — ``opportunities.feature_snapshot`` (§17.3).

    The exact vector with its per-entry quality and provenance, the cut, the
    baseline ids, the regime, every version and the ``state_in``/``state_out`` of
    both hysteresis machines. Recomputing this sample from this dict is the
    guarantee; replaying the intra-minute trajectory is explicitly not.
    """
    cut = ctx.projection.cut
    stage = ctx.stage
    return {
        "as_of": cut.as_of,
        "observation_ts": cut.observation_ts,
        "market": {
            "market_id": str(ctx.market_id),
            "exchange": ctx.vector.exchange,
            "symbol": ctx.vector.symbol,
        },
        "vector": ctx.vector.as_wire(),
        "baseline_ids": [str(item) for item in result.baseline_ids],
        "regime_id": None if regime_id is None else str(regime_id),
        "regime": None if ctx.regime is None else ctx.regime.supporting_features(),
        "regime_stale": ctx.regime_stale,
        "versions": dict(sorted(result.versions.items())),
        "state_in": {
            "stage": None if stage is None else stage.state_in.as_wire(),
            "status": None if status is None else status.get("state_in"),
        },
        "state_out": {
            "stage": None if stage is None else stage.state_out.as_wire(),
            "status": None if status is None else status.get("state_out"),
        },
        "stage": None if stage is None else stage.as_wire(),
        "decomposition": result.decomposition(),
    }


def envelope_bytes(envelope: Mapping[str, Any]) -> bytes:
    """The canonical UTF-8 bytes of an envelope — byte-stable across processes."""
    return canonical_json(dict(envelope))


__all__ = ["envelope_bytes", "opportunity_envelope"]
