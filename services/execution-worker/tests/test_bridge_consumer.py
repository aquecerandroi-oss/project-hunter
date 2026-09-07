"""T3.14 items 1 and 6 — the flag, the group, and what a redelivery does.

The flag is asserted where it actually acts: :func:`bridge_tasks` returns no
task when ``ENABLE_PAPER_AUTONOMY`` is false, so nothing ever calls
``XGROUP CREATE`` and the group does not exist on the stream. The test checks the
*stream*, not a boolean — a worker that creates the group and then refuses to act
still looks, from ``XINFO GROUPS``, like an autonomy that is running.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import text

from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.processed import is_processed
from hunter_core.events.produce import publish
from hunter_core.events.streams import Streams
from hunter_execution_worker.bridge_consumer import (
    CONSUMER_GROUP,
    autonomy_status,
    bridge_tasks,
    handle_signal_event,
    run_bridge_consumer,
)
from hunter_execution_worker.config import ExecutionConfig
from hunter_execution_worker.market_data import SpotSnapshot, StaticSpotMarketData
from hunter_execution_worker.state import CycleHealth

from . import shadow_builders as shadow
from .builders import NOW, book, create_tenant, market_identity, open_wallet, trade

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BAR = NOW - timedelta(seconds=30)
OFF = ExecutionConfig(exit_cost_rate=Decimal(0))
ON = ExecutionConfig(enable_paper_autonomy=True, exit_cost_rate=Decimal(0))


async def _groups(redis: redis_asyncio.Redis) -> list[Any]:
    try:
        return cast(
            "list[Any]", await cast(Any, redis).xinfo_groups(Streams.SHADOW_SIGNALS_EMITTED)
        )
    except Exception:
        return []


async def _lab(factory: async_sessionmaker[AsyncSession], engine: AsyncEngine):  # type: ignore[no-untyped-def]
    tenant = await create_tenant(engine)
    wallet = await open_wallet(factory, engine, tenant)
    perp = await shadow.add_perp_market(engine, tenant)
    version = await shadow.create_version(engine, active=True, at=BAR)
    await shadow.set_spot_volume(engine, tenant.market_id, volume=Decimal(120_000_000))
    await shadow.create_agent(
        engine,
        organization_id=tenant.org_id,
        workspace_id=tenant.workspace_id,
        portfolio_id=wallet.portfolio_id,
        version_id=version,
    )
    await shadow.set_beta(engine, tenant.market_id, as_of=NOW)
    await shadow.ensure_candle_partitions(engine, NOW)
    await shadow.seed_minute_volumes(engine, tenant.market_id, now=NOW)
    signal_id = await shadow.emit_signal(
        engine,
        version_id=version,
        market_id=perp,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_PAPER,
    )
    data = StaticSpotMarketData(
        {
            (tenant.slug, tenant.symbol): SpotSnapshot(
                market=market_identity(tenant),
                book=book(tenant, received_at=NOW),
                trades=(trade(tenant, price=Decimal(100), ts=NOW, trade_id=1),),
                avg_price=Decimal(100),
            )
        }
    )
    return tenant, wallet, signal_id, data


async def _proposals(engine: AsyncEngine, portfolio_id) -> int:  # type: ignore[no-untyped-def]
    async with engine.begin() as connection:
        return cast(
            "int",
            await connection.scalar(
                text("SELECT count(*) FROM trade_proposals WHERE portfolio_id = :pf"),
                {"pf": portfolio_id},
            ),
        )


async def test_with_the_flag_off_no_task_exists_and_the_group_is_never_created(
    redis_client: redis_asyncio.Redis,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert autonomy_status(OFF) == "off"
    tasks = bridge_tasks(
        OFF,
        redis=redis_client,
        factory=db_session_factory,
        data=StaticSpotMarketData({}),
        health=CycleHealth(),
        consumer="probe",
    )
    assert tasks == []
    assert await _groups(redis_client) == []


async def test_the_consumer_turns_one_event_into_one_proposal_and_acks_it(
    redis_client: redis_asyncio.Redis,
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    tenant, wallet, signal_id, data = await _lab(db_session_factory, db_engine)
    health = CycleHealth()
    tasks = bridge_tasks(
        ON,
        redis=redis_client,
        factory=db_session_factory,
        data=data,
        health=health,
        consumer="probe",
    )
    assert [name for name, _coro in tasks] == ["bridge_consumer"]
    for _name, coro in tasks:
        coro.close()  # the wiring is what was asserted; the loop is run below
    await publish(
        redis_client,
        Streams.SHADOW_SIGNALS_EMITTED,
        EventEnvelope(
            event_id=signal_id,
            type=Streams.SHADOW_SIGNALS_EMITTED,
            producer="strategy-worker",
            key=str(signal_id),
            payload={"signal_id": str(signal_id), "purpose": "paper"},
        ),
        1000,
    )
    task = asyncio.create_task(
        run_bridge_consumer(
            redis_client,
            db_session_factory,
            data=data,
            config=ON,
            health=health,
            consumer="probe",
            clock=lambda: NOW,
        )
    )
    try:
        for _ in range(120):
            await asyncio.sleep(0.25)
            if await _proposals(db_engine, wallet.portfolio_id) == 1:
                break
        assert await _proposals(db_engine, wallet.portfolio_id) == 1
        assert await is_processed(redis_client, CONSUMER_GROUP, str(signal_id))
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    names = [
        group["name"].decode() if isinstance(group["name"], bytes) else group["name"]
        for group in await _groups(redis_client)
    ]
    assert names == [CONSUMER_GROUP]
    assert tenant.slug  # the labelled venue, never Binance


async def test_a_redelivered_event_is_a_no_op(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """Even without the ``event_id`` guard: ``client_key`` is ``shadow:{id}``."""
    _tenant, wallet, signal_id, data = await _lab(db_session_factory, db_engine)
    health = CycleHealth()
    payload = {"signal_id": str(signal_id)}
    first = await handle_signal_event(
        db_session_factory, data=data, config=ON, health=health, now=NOW, payload=payload
    )
    second = await handle_signal_event(
        db_session_factory,
        data=data,
        config=ON,
        health=health,
        now=NOW + timedelta(seconds=1),
        payload=payload,
    )
    assert first == 1
    assert second == 0
    assert await _proposals(db_engine, wallet.portfolio_id) == 1
    assert health.bridge_events == 2
