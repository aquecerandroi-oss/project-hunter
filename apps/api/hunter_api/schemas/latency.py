"""``GET /api/v1/system/latency`` — the T3.79 end-to-end budget, published.

Five hops, each read from a heartbeat hash already written by its own worker
(no new DB table, no Prometheus scrape — the same ``HGETALL``-only convention
``hunter_strategy_worker.metrics``/``heartbeat.py`` established in T3.74c, now
shared by ``hunter_market_worker.latency`` and
``hunter_execution_worker.metrics``, T3.79):

- ``ingest`` — ``hb:market:{exchange}``'s ``ingest_lag_p50_s``/``_p95_s``:
  exchange event time to the market-worker's own receive.
- ``flush`` — the same hash's ``flush_lag_p50_s``/``_p95_s``: a closed
  candle's ``close_time`` to it being durably queued for the outbox. Together
  ``ingest`` and ``flush`` are the "exchange event → candle on our stream"
  budget of ``docs/PIPELINE.md`` §6b.
- ``decision`` — ``hb:strategy:shadow``'s ``decision_lag_p50_s``/``_p95_s``
  (T3.74c, not touched by this task): a bar's close to the persisted agent
  decision.
- ``admission`` — ``hb:execution:paper``'s ``admission_lag_p50_s``/``_p95_s``:
  the shadow signal's own ``emitted_at`` to the admission decision persisted.
- ``fill`` — the same hash's ``fill_lag_p50_s``/``_p95_s``: the admission
  decision to the paper fill actually applied.

``end_to_end`` sums the five hops' own p50/p95 — an approximation, not a joint
percentile of the true source-to-fill distribution (summing marginal
quantiles overstates a true joint tail when hops are independent and
understates it when they are correlated). Good enough for a budget dashboard;
not a substitute for tracing one signal through all five timestamps by hand.
``None`` — never a partial sum — the moment any one hop has no p95 yet, since
a sum with a silently-dropped term is not "the whole pipeline is fast", it is
"most of the pipeline is fast and one leg is unmeasured".
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class LatencySloStatus(StrEnum):
    OK = "ok"
    WARN = "warn"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class LatencyHopOut(BaseModel):
    hop: str
    p50_s: float | None = None
    p95_s: float | None = None
    target_p50_s: float
    target_p95_s: float
    status: LatencySloStatus


class ResearchUniverseOut(BaseModel):
    """T3.82: the Shadow Lab's shadow universe -- markets with enough 1m
    history for the replay + replication funnel to ever validate a decision
    on them (``docs/PIPELINE.md`` §6b, ``hunter_strategy_worker.universe``).

    Summed across every ``STRATEGY_SHARDS`` shard's own heartbeat, the same
    union ``_shadow_decision_lag`` already does for the ``decision`` hop --
    each shard owns a disjoint slice of symbols, so a sum (not a max) is the
    cluster-wide count. ``None`` on ``LatencyOut`` itself when no shard has
    published these fields yet (worker not deployed, or
    ``SHADOW_UNIVERSE_MIN_HISTORY_DAYS=0`` disables the gate) -- never a
    fabricated ``0 of 0``.
    """

    markets_in_universe: int
    markets_total: int
    min_history_days: int


class LatencyOut(BaseModel):
    hops: list[LatencyHopOut]
    end_to_end: LatencyHopOut
    generated_at: datetime
    research_universe: ResearchUniverseOut | None = None
