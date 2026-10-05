"""The root cause of the 30/09 and 02/10 stops: a failed cycle must not lose what it collected.

``collect_*`` forgets an episode's id **before** the commit (``collect.py:166``,
``watchdog.py:115``), and ``evaluation_loop`` used to answer *any* exception by
``batch = WriteBatch()``. So one transient error -- a flush, or a Redis
``TimeoutError`` while the *next* market is being read -- erased the ``EXPIRE`` of a
market whose memory had already moved on; the next episode opened under a new id
against a row the database still held open, and ``uq_opportunities_open_per_market``
(or ``uq_anomalies_active_per_market_type``) vetoed every later batch for good
(``obsidian/10-PERFORMANCE/Scanner-lag-2026-10-01.md``, sections 4 and 7).

This test failed against the discarding loop (``assert UUID(...0a) in []``,
05/10/2026, strict ``xfail``); it passes now that ``FlushLane`` keeps the batch.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import SecretStr

from hunter_core.runtime import WorkerRuntime
from hunter_core.settings import Settings
from hunter_scanner_worker import flush_lane, runners
from hunter_scanner_worker.baselines import BaselineCache
from hunter_scanner_worker.config import ScannerConfig
from hunter_scanner_worker.health import CycleHealth
from hunter_scanner_worker.persist import WriteBatch
from hunter_scanner_worker.registry import MarketRef, MarketRegistry
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.state import ScannerState

from .builders import EXCHANGE
from .policies import build_policy
from .test_load import MultiMarketHotState

pytestmark = pytest.mark.unit

EPISODE_X = UUID(int=0xA)


async def test_an_exception_on_the_next_market_does_not_erase_the_expiry_already_collected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refs = [
        MarketRef(market_id=UUID(int=1), exchange=EXCHANGE, symbol="AAAUSDT"),
        MarketRef(market_id=UUID(int=2), exchange=EXCHANGE, symbol="BBBUSDT"),
    ]
    scanner = Scanner(
        config=ScannerConfig(exchange=EXCHANGE, persist_s=0.0),
        policy=build_policy(),
        registry=MarketRegistry(exchange=EXCHANGE),
        state=ScannerState(),
    )
    scanner.registry.apply(refs)
    scanner.cache = BaselineCache(gate=scanner.policy.gate)
    for ref in refs:
        scanner.state.ensure(ref).touch("tick", input_ts=datetime.now(UTC))
    redis = MultiMarketHotState()
    settings = Settings(
        database_url=SecretStr("postgresql+asyncpg://u:p@localhost/x"),
        redis_url=SecretStr("redis://localhost:6379/0"),
    )
    runtime = WorkerRuntime(
        "scanner", settings, engine=cast("Any", None), redis_client=cast("Any", redis)
    )

    calls: dict[str, int] = {"AAAUSDT": 0, "BBBUSDT": 0}

    async def advance(
        self: Scanner, redis: Any, market: Any, batch: WriteBatch, *, now: datetime
    ) -> None:
        symbol = market.ref.symbol
        calls[symbol] += 1
        if symbol == "AAAUSDT" and calls[symbol] == 1:
            # What ``collect_opportunity`` does on EXPIRE: the row goes into the batch
            # and the market forgets the episode, both before any commit.
            batch.opportunities.append({"id": EPISODE_X, "market_id": market.ref.market_id})
            market.opportunity_id = None
        if symbol == "BBBUSDT" and calls[symbol] == 1:
            raise TimeoutError("Timeout reading from redis:6379")

    monkeypatch.setattr(Scanner, "advance", advance)
    persisted: list[UUID] = []

    async def flush(factory: Any, redis: Any, batch: WriteBatch, **kwargs: Any) -> set[UUID]:
        persisted.extend(row["id"] for row in batch.opportunities)
        return set()

    monkeypatch.setattr(flush_lane, "flush_batch", flush)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            runners.evaluation_loop(
                scanner, cast("Any", None), cast("Any", redis), runtime, CycleHealth()
            ),
            1.8,
        )

    assert calls["BBBUSDT"] >= 2, "the premise: the loop recovered from the exception"
    assert EPISODE_X in persisted, "the EXPIRE of episode X was collected and then thrown away"
