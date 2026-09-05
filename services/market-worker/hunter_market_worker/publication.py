"""Best-effort publications with deterministic liquidation identity and visible loss."""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid5

from hunter_core.domain.enums import RiskEventSeverity
from hunter_core.events.produce import publish as core_publish
from hunter_core.logging import get_logger
from hunter_core.observability import market_publish_failures_total
from hunter_market_worker.heartbeat import record_system_event

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.domain.market import NormalizedLiquidation
    from hunter_core.events.envelope import EventEnvelope

NAMESPACE = UUID("6f2e6c9a-2a9d-4f7d-9a2c-6e6a2f6b0a11")
publication_sessions: ContextVar[async_sessionmaker[AsyncSession] | None] = ContextVar(
    "market_publication_sessions", default=None
)
logger = get_logger(__name__)


def liquidation_id(event: NormalizedLiquidation) -> UUID:
    def decimal_text(value: Any) -> str:
        value = format(value, "f")
        return value.rstrip("0").rstrip(".") if "." in value else value

    ts_ms = int(event.ts.timestamp()) * 1000 + event.ts.microsecond // 1000
    canonical = json.dumps(
        [
            event.exchange,
            event.symbol,
            event.side.value,
            decimal_text(event.price),
            decimal_text(event.qty),
            ts_ms,
        ],
        separators=(",", ":"),
    )
    return uuid5(NAMESPACE, canonical)


async def publish(
    client: Any, stream: str, envelope: EventEnvelope, maxlen: int
) -> bytes | str | None:
    try:
        return await core_publish(client, stream, envelope, maxlen)
    except Exception:
        market_publish_failures_total.labels(stream=stream).inc()
        logger.exception("market_publish_failed", stream=stream, event_id=str(envelope.event_id))
        factory = publication_sessions.get()
        if factory is not None:
            await record_system_event(
                factory,
                "market_publish_failed",
                f"{stream} event_id={envelope.event_id}",
                RiskEventSeverity.WARNING,
            )
        return None
