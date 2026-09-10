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

import functools
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketType, Timeframe
from hunter_core.domain.market import NormalizedCandle, to_wire
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
