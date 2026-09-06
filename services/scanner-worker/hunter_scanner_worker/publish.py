"""The ephemeral half of publication: hot state, ``radar:scores`` and pub/sub.

Two classes of publication, and the difference is deliberate:

- **durable** -- ``anomalies.detected``, ``regime.changed``,
  ``opportunities.updated`` -- go through the transactional outbox, in the same
  commit as the row they describe (``persist.py``). A consumer of those is
  entitled to assume the database agrees.
- **ephemeral** -- ``features.updated``, ``rt:radar``, ``feat:*``, ``opp:*``,
  ``radar:scores``, ``regime:current`` -- are projections of state that is
  already durable somewhere else. Losing one costs a refresh, never a fact
  (ARCHITECTURE.md section 5.3), so they are written directly and a failure is
  logged rather than retried into the latency budget.

``features.updated`` is on the ephemeral side even though ``PIPELINE.md``
section 3 names it as the anomaly trigger: inside this process the pipeline runs
in one pass over one cut (``evaluate.py``), and the stream is what *other*
consumers subscribe to.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import orjson

from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.produce import publish as xadd
from hunter_core.events.streams import DEFAULT_MAXLEN, Streams
from hunter_core.logging import get_logger
from hunter_core.redis import keys

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

    from hunter_indicators.regime import RegimeDecision
    from hunter_scanner_worker.evaluate import Evaluation
    from hunter_scanner_worker.registry import MarketRef

logger = get_logger(__name__)

RADAR_CHANNEL = "rt:radar"
FEATURE_TTL_S = 300
"""A feature projection nobody refreshed for five minutes is not current, and a
reader must not be able to mistake it for current."""

__all__ = [
    "FEATURE_TTL_S",
    "RADAR_CHANNEL",
    "publish_features",
    "publish_radar",
    "publish_regime_current",
]


async def publish_features(
    redis: redis_asyncio.Redis, producer: str, ref: MarketRef, evaluation: Evaluation
) -> None:
    """``feat:{exchange}:{symbol}`` plus the ``features.updated`` notification."""
    vector = evaluation.vector
    payload: dict[str, Any] = {
        "market_id": str(ref.market_id),
        "exchange": ref.exchange,
        "symbol": ref.symbol,
        "ts": vector.ts.isoformat(),
        "feature_set_version": vector.feature_set_version,
    }
    body = vector.as_json()
    try:
        key = keys.features(ref.exchange, ref.symbol)
        await cast(Any, redis).set(key, orjson.dumps(body), ex=FEATURE_TTL_S)
        await xadd(
            redis,
            Streams.FEATURES_UPDATED,
            EventEnvelope(
                type=Streams.FEATURES_UPDATED,
                producer=producer,
                key=f"{ref.exchange}:{ref.symbol}",
                payload=payload,
            ),
            DEFAULT_MAXLEN[Streams.FEATURES_UPDATED],
        )
    except Exception:
        # Ephemeral by definition: the vector is already on its way to
        # ``feature_snapshots`` and the score does not depend on this write.
        logger.warning("scanner_feature_publish_failed", symbol=ref.symbol)


async def publish_radar(redis: redis_asyncio.Redis, ref: MarketRef, evaluation: Evaluation) -> None:
    """``radar:scores`` (ZSET), ``opp:*`` and the ``rt:radar`` broadcast."""
    score = evaluation.score
    state = evaluation.status.state_out if evaluation.status is not None else None
    if score is None or state is None or score.score is None:
        # Nothing to project: a market with no eligible evidence keeps whatever
        # the Radar last showed, stamped by its own ``last_updated_at``. Writing
        # a zero here is the one thing that must not happen.
        return
    member = f"{ref.exchange}:{ref.symbol}"
    payload: dict[str, Any] = {
        "market_id": str(ref.market_id),
        "exchange": ref.exchange,
        "symbol": ref.symbol,
        "score": str(state.score),
        "confidence": str(score.confidence),
        "status": state.status.value,
        "stage": state.stage.value,
        "direction": state.direction.value,
        "eligible": score.eligible,
        "observation_ts": evaluation.observation_ts.isoformat(),
    }
    try:
        await cast(Any, redis).zadd(keys.radar_scores(), {member: float(state.score)})
        await cast(Any, redis).set(
            keys.opportunity(ref.exchange, ref.symbol), orjson.dumps(payload), ex=FEATURE_TTL_S
        )
        await cast(Any, redis).publish(RADAR_CHANNEL, orjson.dumps(payload))
    except Exception:
        logger.warning("scanner_radar_publish_failed", symbol=ref.symbol)


async def drop_from_radar(redis: redis_asyncio.Redis, ref: MarketRef) -> None:
    """A market that left the universe stops being a row on the Radar.

    Leaving it in the ZSET would keep showing a score nobody is refreshing --
    the "fake anything" this product forbids, arrived by omission.
    """
    try:
        await cast(Any, redis).zrem(keys.radar_scores(), f"{ref.exchange}:{ref.symbol}")
        await cast(Any, redis).delete(keys.opportunity(ref.exchange, ref.symbol))
    except Exception:
        logger.warning("scanner_radar_drop_failed", symbol=ref.symbol)


async def publish_regime_current(
    redis: redis_asyncio.Redis, decision: RegimeDecision, *, regime_id: str | None
) -> None:
    """``regime:current`` -- the pair, the label and how confident the pair is."""
    trend, volatility = decision.state_out.pair
    payload = {
        "regime_id": regime_id,
        "regime": decision.state_out.regime.value,
        "trend": trend.value,
        "volatility": volatility.value,
        "confidence": None if decision.confidence is None else str(decision.confidence),
        "observation_ts": decision.observation_ts.isoformat(),
        "classifier_version": decision.classifier_version,
    }
    try:
        await cast(Any, redis).set(keys.regime_current(), orjson.dumps(payload))
    except Exception:
        logger.warning("scanner_regime_publish_failed")
