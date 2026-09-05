"""Realized funding requires a REST settlement history, never a WS rate estimate."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from hunter_core.db.models.market_data import FundingRate
from hunter_core.db.session import role_session
from hunter_core.domain.enums import RiskEventSeverity
from hunter_core.domain.market import to_wire
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.streams import DEFAULT_MAXLEN, Streams
from hunter_core.logging import get_logger
from hunter_market_worker.heartbeat import record_system_event
from hunter_market_worker.hot_state import write_funding
from hunter_market_worker.persist_rows import load_market_ids
from hunter_market_worker.publication import publish
from hunter_market_worker.queues import RealizedFunding
from hunter_market_worker.recovery import server_now

logger = get_logger(__name__)


async def poll_realized(
    factory: Any, adapter: Any, redis: Any, universe: Any, queues: Any, producer: str
) -> None:
    """Optional adapter hook fetch_realized_funding(symbol,start,end).

    Each returned NormalizedFunding.ts is the settlement time, sourced from
    realized REST history. This explicit capability is absent from T1.2 today.
    """
    now = await server_now(adapter)
    async with role_session(factory, db_role="hunter_worker") as session:
        ids = await load_market_ids(session, adapter.code, set(universe.symbols))
        # MEDIUM-6: one GROUP BY for every monitored market's watermark
        # instead of one round trip per market; markets with no history yet
        # keep their None watermark (absent from the grouped rows).
        watermarks: dict[Any, Any] = {}
        if ids:
            rows = (
                await session.execute(
                    select(FundingRate.market_id, func.max(FundingRate.funding_time))
                    .where(FundingRate.market_id.in_(ids.values()))
                    .group_by(FundingRate.market_id)
                )
            ).all()
            watermarks = {row[0]: row[1] for row in rows}
        starts = {symbol: watermarks.get(market_id) for symbol, market_id in ids.items()}
    for symbol, watermark in starts.items():
        records = await adapter.fetch_realized_funding(
            symbol, watermark or now - timedelta(days=1), now
        )
        for record in records:
            if record.symbol != symbol or record.exchange != adapter.code or record.ts > now:
                continue
            if watermark is not None and record.ts <= watermark:
                continue
            realized = RealizedFunding.model_validate(to_wire(record))
            queues.events.put_nowait(realized)
            await write_funding(redis, realized, realized=True)
            payload = to_wire(realized)
            payload["funding_kind"] = "realized"
            envelope = EventEnvelope(
                type=Streams.MARKET_DERIVATIVES,
                producer=producer,
                key=f"{adapter.code}:{symbol}",
                payload=payload,
            )
            await publish(redis, envelope.type, envelope, DEFAULT_MAXLEN[envelope.type])


async def run_funding(
    factory: Any, adapter: Any, redis: Any, universe: Any, queues: Any, settings: Any, runtime: Any
) -> None:
    if not callable(getattr(adapter, "fetch_realized_funding", None)):
        logger.error("market_realized_funding_unavailable", exchange=adapter.code)
        await record_system_event(
            factory,
            "realized_funding_unavailable",
            "adapter lacks fetch_realized_funding; estimated rates will not be persisted as realized",
            RiskEventSeverity.WARNING,
        )
        await asyncio.Event().wait()
    while True:
        if universe.symbols:
            try:
                await poll_realized(
                    factory, adapter, redis, universe, queues, f"market-worker@{runtime.instance}"
                )
            except Exception:
                runtime.mark_error()
                logger.exception("market_realized_funding_failed")
        await asyncio.sleep(settings.market_oi_poll_s)
