"""Deterministic identity of a shadow signal — SHADOW-LAB.md §6.

    agent_signals.id = uuid5(NAMESPACE_SHADOW,
        canonical(strategy_version_id, market_id, params_hash, source_bar_close, cohort))

Five things and no more. ``decision_at`` is **outside** the hash on purpose: the
same observation decided twice (a redelivery, a restart, a replayed backlog) has
to land on the same row so ``INSERT ... ON CONFLICT (id) DO NOTHING``
de-duplicates it, and the wall clock of the second attempt must not create a
second signal. The cohort *is* inside, so a replay never collides with the
prospective population it is not allowed to contaminate.

The bytes come from ``hunter_core.strategies.canonical`` (``params_format = 1``),
so two equivalent spellings of the same instant produce the same id and a naive
timestamp is refused instead of assumed.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from hunter_core.strategies.canonical import canonical_json

NAMESPACE_SHADOW = uuid.UUID("0f9d2a3c-5b7e-5c41-9f3a-8d6c1e2b4a70")
"""Pinned forever: changing it renumbers every signal ever emitted."""

__all__ = ["NAMESPACE_SHADOW", "signal_id"]


def signal_id(
    *,
    strategy_version_id: uuid.UUID,
    market_id: uuid.UUID,
    params_hash: str,
    source_bar_close: datetime,
    cohort: str,
) -> uuid.UUID:
    """The identity of one shadow decision (also its ``shadow_outbox.event_id``)."""
    name = canonical_json(
        {
            "cohort": cohort,
            "market_id": market_id,
            "params_hash": params_hash,
            "source_bar_close": source_bar_close,
            "strategy_version_id": strategy_version_id,
        }
    ).decode("utf-8")
    return uuid.uuid5(NAMESPACE_SHADOW, name)
