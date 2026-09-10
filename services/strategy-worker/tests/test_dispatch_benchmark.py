"""Concurrent dispatch against real Postgres: decisions survive unchanged (T3.74c).

**Why a small market count, not the 11 x 200 the brief names.** That shape is
what T3.74 measured live and what the *dispatcher itself* is benchmarked
against, at ``test_dispatch.py::TestThroughputAtTheMeasuredShape`` — with
simulated per-bar cost, so the comparison is about the concurrency mechanism,
not about this container's disk. Running 2 200 *real* ``evaluate_slot`` calls
against Postgres would take, at T3.74b's own measured ~1.4/s, the better part
of half an hour per pass — not a test, and not what this file is for. What a
real database can and must prove is different: that handling several markets
*concurrently*, each opening its own sessions against the *same* Postgres
container at the same time, produces the exact decisions serial handling
would have — no cross-market leakage, no corrupted read under concurrent
transactions. Five markets (one with a real trigger, four quiet) is enough to
exercise that; a wider fan-out would not make the proof stronger, only slower.

**Design.** ``consumer.evaluate_slot`` is wrapped (not replaced) to record
every real :class:`~hunter_core.strategies.base.Evaluation` it returns, keyed
by ``(symbol, version.version)``. The same five candles, at the same
``bar_close``, are delivered once through ``handle_candle`` called serially
(concurrency effectively 1) and once through :class:`BarDispatcher` at
concurrency 4. ``Evaluation`` is computed before any slot lock or persistence
(``decide.py``; the same property ``test_context_cache_engine.py``'s
``TestEquivalence`` already relies on for T3.74b), so calling it twice for the
same bar never corrupts the comparison — only the second pass's *persistence*
is a no-op once the slot barrier has moved.
"""

from __future__ import annotations

import asyncio
import functools
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketType, Timeframe
from hunter_core.domain.market import NormalizedCandle, to_wire
from hunter_core.logging import get_logger
from hunter_core.strategies.base import Evaluation
from hunter_core.strategies.canonical import params_hash
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1
from hunter_strategy_worker import consumer as consumer_module
from hunter_strategy_worker.catalogue import ActiveVersion
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.consumer import ConsumerHealth, handle_candle
from hunter_strategy_worker.decide import evaluate_slot as real_evaluate_slot
from hunter_strategy_worker.dispatch import BarDispatcher, market_key
from hunter_strategy_worker.repo import load_market

from .builders import (
    EXCHANGE,
    activate_version,
    ensure_partitions,
    insert_candles,
    seed_market,
    series,
)

pytestmark = pytest.mark.integration

LATE = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)
CONFIG = ShadowConfig(hot_state_tail=0)
MARKET_COUNT = 5
SPIKE_MARKET_INDEX = 2


def _version(key: str, version_id: uuid.UUID, *, version: str) -> ActiveVersion:
    frozen = dict(VOLUME_ANOMALY_V1.default_parameters)
    return ActiveVersion(
        id=version_id,
        strategy_key=key,
        version=version,
        params=frozen,
        params_hash=params_hash(frozen),
        strategy=VOLUME_ANOMALY_V1,
        code_ref=None,
        purpose="research_only",
    )


class _Versions:
    def __init__(self, versions: list[ActiveVersion]) -> None:
        self._versions = versions

    async def get(self, _factory: Any) -> list[ActiveVersion]:
        return list(self._versions)


def _recording_evaluate_slot(sink: dict[tuple[str, str], Evaluation]) -> Any:
    async def wrapper(*args: Any, market: Any, version: ActiveVersion, **kwargs: Any) -> Evaluation:
        evaluation = await real_evaluate_slot(*args, market=market, version=version, **kwargs)
        sink[(market.symbol, version.version)] = evaluation
        return evaluation

    return wrapper


@pytest.fixture
async def markets(db_session_factory: Any) -> list[Any]:
    """``MARKET_COUNT`` perpetuals; only :data:`SPIKE_MARKET_INDEX` triggers."""
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, LATE)
    symbols = [f"DISPATCH{i}USDT" for i in range(MARKET_COUNT)]
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(text("DELETE FROM shadow_outbox"))
        await session.execute(text("DELETE FROM shadow_episodes"))
        await session.execute(text("DELETE FROM signal_outcomes"))
        await session.execute(text("DELETE FROM agent_signals"))
        await session.execute(text("DELETE FROM candles"))
        for index, symbol in enumerate(symbols):
            _exchange_id, market_id = await seed_market(session, symbol=symbol, base_asset="BTC")
            spike = index == SPIKE_MARKET_INDEX
            await insert_candles(session, market_id, series(LATE, trigger=spike))
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = [await load_market(session, EXCHANGE, symbol) for symbol in symbols]
    assert all(row is not None for row in rows)
    return rows


@pytest.fixture
async def versions(db_session_factory: Any) -> list[ActiveVersion]:
    """A small family (3 versions) so the T3.74b context cache is exercised
    alongside concurrency, not instead of it."""
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        ids = [
            (await activate_version(session, key="dispatch_family", version=f"v{i}"))[1]
            for i in range(1, 4)
        ]
    return [_version("dispatch_family", ids[i], version=f"v{i + 1}") for i in range(3)]


async def _deliver_all(
    factory: Any,
    redis: Any,
    markets_list: list[Any],
    versions_list: list[ActiveVersion],
    *,
    concurrency: int,
) -> ConsumerHealth:
    health = ConsumerHealth()
    clock = lambda: LATE + timedelta(seconds=2)  # noqa: E731

    async def _handle(market: Any) -> None:
        payload = to_wire(
            NormalizedCandle(
                exchange=market.exchange,
                symbol=market.symbol,
                market_type=MarketType.PERPETUAL,
                timeframe=Timeframe.M1,
                open_time=LATE - timedelta(minutes=1),
                close_time=LATE,
                open=Decimal("100"),
                high=Decimal("100.4"),
                low=Decimal("99.8"),
                close=Decimal("100"),
                volume=Decimal("60"),
                is_final=True,
            )
        )
        await handle_candle(
            factory,
            redis,
            payload=payload,
            versions=_Versions(versions_list),  # type: ignore[arg-type]
            config=CONFIG,
            health=health,
            clock=clock,
        )

    if concurrency == 1:
        for market in markets_list:
            await _handle(market)
    else:
        dispatcher = BarDispatcher(concurrency=concurrency)
        for market in markets_list:
            await dispatcher.submit(
                market_key(
                    {
                        "exchange": market.exchange,
                        "symbol": market.symbol,
                        "market_type": "perpetual",
                    }
                ),
                f"msg-{market.symbol}",
                functools.partial(_handle, market),
            )
        await dispatcher.drain()
    return health


class TestConcurrentDispatchAgreesWithSerial:
    async def test_every_markets_decision_is_byte_identical_serial_vs_concurrent(
        self,
        db_session_factory: Any,
        redis_client: Any,
        markets: list[Any],
        versions: list[ActiveVersion],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        serial_sink: dict[tuple[str, str], Evaluation] = {}
        monkeypatch.setattr(consumer_module, "evaluate_slot", _recording_evaluate_slot(serial_sink))
        await _deliver_all(db_session_factory, redis_client, markets, versions, concurrency=1)
        assert len(serial_sink) == MARKET_COUNT * len(versions)

        concurrent_sink: dict[tuple[str, str], Evaluation] = {}
        monkeypatch.setattr(
            consumer_module, "evaluate_slot", _recording_evaluate_slot(concurrent_sink)
        )
        await _deliver_all(db_session_factory, redis_client, markets, versions, concurrency=4)
        assert len(concurrent_sink) == MARKET_COUNT * len(versions)

        assert set(serial_sink) == set(concurrent_sink)
        for key, before in serial_sink.items():
            after = concurrent_sink[key]
            assert after.state == before.state, key
            assert after.reason == before.reason, key
            assert after.decision == before.decision, key

        spike_symbol = markets[SPIKE_MARKET_INDEX].symbol
        triggered = [key for key in serial_sink if key[0] == spike_symbol]
        assert any(serial_sink[key].state.value == "triggered" for key in triggered), (
            "the one designed-to-trigger market produced no TRIGGERED evaluation at all"
        )


_CONTENDER_SCRIPT = """
import asyncio, hashlib, os, sys, time
import asyncpg

url, duration_s, connections = sys.argv[1], float(sys.argv[2]), int(sys.argv[3])


async def hammer() -> None:
    conn = await asyncpg.connect(url)
    try:
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            await conn.fetchval("SELECT 1")
            hashlib.sha256(os.urandom(4096)).digest()  # stand-in for Decimal-heavy work
    finally:
        await conn.close()


async def main() -> None:
    await asyncio.gather(*(hammer() for _ in range(connections)))


asyncio.run(main())
"""
"""A separate OS process (T3.80), never imported from this test module -- a
plain ``python -c`` script started with :func:`subprocess.Popen`, exactly the
shape a real replay is (``python -m hunter_strategy_worker.replay.run``, its
own process, not a thread or a task in this loop). It opens its own
connections to the SAME testcontainer Postgres this test's own dispatch uses
and spends CPU on every iteration -- the two resources T3.76 measured the live
lane losing to a replay that shared its container (CPU and DB pool)."""


class TestSurvivesAConcurrentReplayProcess:
    """T3.80: a replay running as its own OS process, contending for the SAME
    Postgres, must not push the live dispatch's own drain past its p95 budget
    (< 20 s, T3.74c, ``docs/PIPELINE.md`` §6c "Orçamento de latência").

    T3.76 measured the opposite when the replay shared the live worker's own
    *container* — median decision lag 26 s -> 90 s, p95 -> 171 s. This proves
    the mechanism this task's fix actually relies on (a *separate* OS process,
    its own smaller DB pool) does not reproduce that failure against the
    closest thing to production this suite has: a real Postgres, real
    concurrent connections from a second process, real CPU contention on the
    same host.

    **What this does not prove**, honestly: it does not reproduce the VPS's
    cgroup CPU/memory ceiling (``replay-worker``'s ``deploy.resources.limits``,
    ``infra/docker/docker-compose.yml``) or the VPS's own core count and disk —
    a container limit changes *how much* contention is even possible, and a
    dev machine's core count/disk shape are not the VPS's. That half of the
    proof is the live measurement this task's notes (`.claude/state/
    notes-T3.80.md`) ask the orchestrator to take after this deploys: run
    ``compose.sh replay ...`` concurrently with the live worker for one window
    and read `decision_lag_p50_s`/`_p95_s` off `hb:strategy:shadow` during it,
    expecting them to stay under `ShadowConfig`'s 10 s/30 s thresholds — unlike
    the 90 s/171 s the `docker exec`-into-the-container run produced.
    """

    CONTENTION_CONNECTIONS = 3
    """One below ``REPLAY_MAX_WORKERS``'s default (4): the live dispatch in
    this same test already holds sessions of its own against the same pool,
    so 3 + the live side's own connections still fits comfortably under
    ``db_pool_size + db_max_overflow`` (5 + 5 = 10, ``Settings``)."""
    ROUNDS = 6
    CONTENTION_DURATION_S = 40.0

    async def test_the_live_drain_p95_stays_under_budget_with_a_concurrent_replay(
        self,
        db_session_factory: Any,
        redis_client: Any,
        markets: list[Any],
        versions: list[ActiveVersion],
        migrated_db_url: str,
    ) -> None:
        plain_url = migrated_db_url.replace("postgresql+asyncpg://", "postgresql://")
        process = subprocess.Popen(  # noqa: ASYNC220 -- Popen itself doesn't block; wait() below does, off-loop
            [
                sys.executable,
                "-c",
                _CONTENDER_SCRIPT,
                plain_url,
                str(self.CONTENTION_DURATION_S),
                str(self.CONTENTION_CONNECTIONS),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            await asyncio.sleep(1.0)  # let the contention actually ramp up first
            assert process.poll() is None, "the contending process exited early"
            durations: list[float] = []
            for _ in range(self.ROUNDS):
                started = time.perf_counter()
                await _deliver_all(
                    db_session_factory, redis_client, markets, versions, concurrency=8
                )
                durations.append(time.perf_counter() - started)
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

        durations.sort()
        p95 = durations[int(0.95 * (len(durations) - 1))]
        get_logger(__name__).info(
            "t380_replay_contention_proof",
            durations_s=[round(d, 2) for d in durations],
            p95_s=round(p95, 2),
        )
        assert p95 < 20.0, (
            f"live drain p95={p95:.2f}s with a concurrent replay process on the "
            f"same host -- durations={[f'{d:.2f}' for d in durations]}"
        )
