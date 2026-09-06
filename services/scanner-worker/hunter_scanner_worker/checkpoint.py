"""The warm checkpoint of one market: ATR anchor, stage hysteresis, last sample.

Three states have no column of their own anywhere in the schema, because they
are not facts about the market — they are facts about *this* recursion over it:
the anchored ATR (``notes-T2.2`` §4), the stage hysteresis (``notes-T2.3`` §15a)
and the last history mark the sampling rule compares against. They live in
``scan:state:{exchange}:{symbol}``.

**Redis, and the cost is declared.** ARCHITECTURE.md §5.3 says what is in Redis
may be lost; here is exactly what that costs, and it is bounded: the ATR
re-anchors on the bars the context can prove (a slightly different number, and
the checkpoint says so through ``origin_reason``), and the stage falls back to
``NONE`` and needs its two confirming observations again. What it must **not**
do is pretend: a rehydrated state carries ``recovered``, and a state that was
lost is spelled ``cold`` rather than being confused with a first start. The
distinction matters because ``advance_from_context`` reports ``bootstrap`` for
both, so only this module can tell an operator which one happened.

Nothing durable depends on this file: the anomaly cycle lives in ``anomalies``,
the episode in ``opportunities`` and the regime in ``market_regimes``. Losing
Redis loses precision, never evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import orjson

from hunter_core.domain.enums import OpportunityStage, OpportunityStatus, TradeDirection
from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger
from hunter_core.redis import keys
from hunter_indicators.features import EMPTY_STATE, FeatureState
from hunter_indicators.opportunity import HistoryMark
from hunter_indicators.stage import EMPTY_STAGE_STATE, StageState

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

logger = get_logger(__name__)

CHECKPOINT_VERSION = 1
CHECKPOINT_TTL_S = 7 * 24 * 60 * 60
"""A market that left the universe a week ago restarts cold rather than
resuming a hysteresis from a different market regime."""

__all__ = [
    "CHECKPOINT_TTL_S",
    "CHECKPOINT_VERSION",
    "Checkpoint",
    "history_mark_from_wire",
    "load_checkpoint",
    "save_checkpoint",
    "stage_state_from_wire",
]


def _ts(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    return ensure_utc(datetime.fromisoformat(str(value)))


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def stage_state_from_wire(wire: dict[str, Any]) -> StageState:
    """Rebuild a :class:`StageState` from its ``as_wire()``.

    T2.3 ships the serializer and not the parser (nothing in ``hunter_indicators``
    ever reads a state back), so the inverse lives here, next to the only process
    that restarts.
    """
    return StageState(
        stage=OpportunityStage(wire["stage"]),
        basis=str(wire.get("basis") or ""),
        candidate=OpportunityStage(wire["candidate"]),
        confirmations=int(wire.get("confirmations") or 0),
        last_observation_ts=_ts(wire.get("last_observation_ts")),
        direction=TradeDirection(wire.get("direction") or TradeDirection.NEUTRAL.value),
        candidate_direction=TradeDirection(
            wire.get("candidate_direction") or TradeDirection.NEUTRAL.value
        ),
        unsupported=int(wire.get("unsupported") or 0),
    )


def history_mark_from_wire(wire: dict[str, Any]) -> HistoryMark:
    """Rebuild the last persisted sample the history rule compares against."""
    ts = _ts(wire.get("ts"))
    if ts is None:
        raise ValueError("a history mark without a ts cannot be compared against")
    return HistoryMark(
        ts=ts,
        score=_decimal(wire.get("score")),
        status=OpportunityStatus(wire["status"]),
        stage=OpportunityStage(wire.get("stage") or OpportunityStage.NONE.value),
        direction=TradeDirection(wire.get("direction") or TradeDirection.NEUTRAL.value),
        stage_direction=TradeDirection(wire.get("stage_direction") or TradeDirection.NEUTRAL.value),
        regime=str(wire.get("regime") or ""),
        quality=str(wire.get("quality") or ""),
        eligible=bool(wire.get("eligible", True)),
        versions=dict(wire.get("versions") or {}),
    )


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """What a restarting scanner can recover about one market."""

    features: FeatureState = EMPTY_STATE
    stage: StageState = EMPTY_STAGE_STATE
    history: HistoryMark | None = None
    recovered: bool = False
    """``False`` means cold: nothing was stored, so the ATR anchor and the stage
    hysteresis start over. Reported, never hidden."""

    def as_wire(self) -> dict[str, Any]:
        return {
            "version": CHECKPOINT_VERSION,
            "features": self.features.as_wire(),
            "stage": self.stage.as_wire(),
            "history": None if self.history is None else self.history.as_wire(),
        }


def _default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"{type(value)!r} is not serialisable in a checkpoint")


async def save_checkpoint(
    redis: redis_asyncio.Redis, exchange: str, symbol: str, checkpoint: Checkpoint
) -> None:
    key = keys.scanner_state(exchange, symbol)
    payload = orjson.dumps(checkpoint.as_wire(), default=_default)
    await cast(Any, redis).set(key, payload, ex=CHECKPOINT_TTL_S)


async def load_checkpoint(redis: redis_asyncio.Redis, exchange: str, symbol: str) -> Checkpoint:
    """Rehydrate one market. A corrupt or foreign-version payload starts cold."""
    raw: Any = await cast(Any, redis).get(keys.scanner_state(exchange, symbol))
    if not raw:
        return Checkpoint()
    try:
        wire: dict[str, Any] = orjson.loads(raw)
        if int(wire.get("version") or 0) != CHECKPOINT_VERSION:
            return Checkpoint()
        history = wire.get("history")
        return Checkpoint(
            features=FeatureState.from_wire(dict(wire.get("features") or {})),
            stage=stage_state_from_wire(dict(wire.get("stage") or {}))
            if wire.get("stage")
            else EMPTY_STAGE_STATE,
            history=history_mark_from_wire(dict(history)) if history else None,
            recovered=True,
        )
    except Exception:
        # A checkpoint that cannot be read is a cold start with a log line, not
        # a crash loop: the durable evidence is untouched either way.
        logger.warning("scanner_checkpoint_unreadable", exchange=exchange, symbol=symbol)
        return Checkpoint()
