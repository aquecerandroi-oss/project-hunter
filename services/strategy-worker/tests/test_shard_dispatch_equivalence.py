"""Two shards over the real stream agree with one worker, byte-identical,
with no duplicates (T3.74f).

**Design.** The same real ``market.candles.closed`` events (one per market,
published once to a real Redis stream backed by a testcontainer) are drained
twice: once by a single unsharded ``run_consumer`` (``shard_total=1``, one
consumer group), once by two ``run_consumer`` tasks running *concurrently*,
each its own shard (``shard_index=0/1``, ``shard_total=2``, each its own
consumer group -- ``hunter_strategy_worker.shard.consumer_group``). Redis
consumer groups are independent cursors over the same stream (created at
``id="0"``, ``hunter_core.events.produce.ensure_group``), so publishing once
and draining it with two different group topologies proves the same thing a
production deploy relies on: creating new, per-shard groups on the stream the
unsharded deployment already uses does not require replaying anything.

``consumer.evaluate_slot`` is wrapped (not replaced) to record every real
:class:`~hunter_core.strategies.base.Evaluation`, keyed by ``(symbol,
version.version)`` -- the same technique ``test_dispatch_benchmark.py`` uses,
computed before any slot lock or persistence, so calling the same bar twice
(once per pass) never corrupts the comparison. Recording into a *list* per
key, not overwriting a dict entry, is what makes "no duplicates" a real
assertion here rather than an accident of dict semantics: if a bar were ever
evaluated by more than one shard, the list would have more than one entry.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketType, Timeframe
from hunter_core.domain.market import NormalizedCandle, to_wire
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.produce import publish
from hunter_core.events.streams import Streams
from hunter_core.strategies.base import Evaluation
from hunter_strategy_worker import consumer as consumer_module
from hunter_strategy_worker.catalogue import ActiveVersion
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.consumer import ConsumerHealth, run_consumer
from hunter_strategy_worker.decide import evaluate_slot as real_evaluate_slot
from hunter_strategy_worker.repo import load_market
from hunter_strategy_worker.shard import owns_market

from .builders import (
    EXCHANGE,
    activate_version,
    ensure_partitions,
    insert_candles,
    isolate_catalogue,
    seed_market,
    series,
)

pytestmark = pytest.mark.integration

LATE = datetime(2026, 9, 10, 11, 0, tzinfo=UTC)
SHARD_TOTAL = 2
SPIKE_MARKET_INDEX = 2
POLL_S = 0.05
DRAIN_TIMEOUT_S = 20.0


def _symbols() -> list[str]:
    """A fixed set that provably splits across both shards of
    ``SHARD_TOTAL`` -- asserted in the fixture, not assumed, so a future
    change to :func:`hunter_core.sharding.owns` that broke the split would
    fail loudly here rather than silently testing only one shard."""
    return [f"SHARDEQ{i}USDT" for i in range(6)]


class _Runtime:
    """``WorkerRuntime``-shaped enough for ``run_consumer``: it only reads
    ``.instance`` and calls ``.mark_error()``/``.mark_success()``."""

    def __init__(self, instance: str) -> None:
        self.instance = instance

    def mark_error(self) -> None:
        pass

    def mark_success(self) -> None:
        pass


def _recording_evaluate_slot(sink: dict[tuple[str, str], list[Evaluation]]) -> Any:
    async def wrapper(*args: Any, market: Any, version: ActiveVersion, **kwargs: Any) -> Evaluation:
        evaluation = await real_evaluate_slot(*args, market=market, version=version, **kwargs)
        sink.setdefault((market.symbol, version.version), []).append(evaluation)
        return evaluation

    return wrapper


@pytest.fixture
async def markets(db_session_factory: Any) -> list[Any]:
    symbols = _symbols()
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, LATE)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(text("DELETE FROM shadow_outbox"))
        await session.execute(text("DELETE FROM shadow_episodes"))
        await session.execute(text("DELETE FROM signal_outcomes"))
        await session.execute(text("DELETE FROM agent_signals"))
        await session.execute(text("DELETE FROM candles"))
        for index, symbol in enumerate(symbols):
            _exchange_id, market_id = await seed_market(session, symbol=symbol, base_asset="BTC")
            await insert_candles(
                session, market_id, series(LATE, trigger=index == SPIKE_MARKET_INDEX)
            )
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = [await load_market(session, EXCHANGE, symbol) for symbol in symbols]
    assert all(row is not None for row in rows)
    owners = {owns_market(s, i, SHARD_TOTAL) for i in range(SHARD_TOTAL) for s in symbols}
    assert owners == {True, False}, "the fixture's symbols must exercise both shards, not just one"
    return rows


VERSION_COUNT = 2
"""Real, activated ``strategy_versions`` rows -- ``run_consumer`` loads the
roster from the database itself (:class:`hunter_strategy_worker.versions.
VersionCache`), so this fixture activates the family it does through
``activate_version``/``isolate_catalogue`` and never builds an
:class:`ActiveVersion` object by hand the way the pure-``handle_candle``
tests (``test_dispatch_benchmark.py``) can afford to."""


@pytest.fixture
async def versions(db_session_factory: Any) -> int:
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        for i in range(1, VERSION_COUNT + 1):
            await activate_version(session, key="shardeq_family", version=f"v{i}")
        await isolate_catalogue(session, keep="shardeq_family")
    return VERSION_COUNT


async def _publish_all(redis: Any, markets_list: list[Any]) -> None:
    for market in markets_list:
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
        envelope = EventEnvelope(
            type="market.candles.closed",
            producer="test",
            key=f"{market.exchange}:{market.symbol}",
            payload=payload,
        )
        await publish(redis, Streams.MARKET_CANDLES_CLOSED, envelope, maxlen=10_000)


async def _drain(
    factory: Any,
    redis: Any,
    *,
    expected: int,
    shards: list[tuple[int, int]],
    sink: dict[tuple[str, str], list[Evaluation]],
) -> None:
    """Run one ``run_consumer`` per ``(shard_index, shard_total)`` pair
    concurrently until ``sink`` has ``expected`` keys, then cancel all of
    them. A fixed clock keeps every bar comfortably inside
    ``late_delay_backlog_max_s``/``eligibility_max_lag_s`` regardless of how
    long the real drain takes."""
    clock = lambda: LATE + timedelta(seconds=2)  # noqa: E731
    tasks = [
        asyncio.ensure_future(
            run_consumer(
                factory,
                redis,
                _Runtime(f"shard-{index}of{total}"),  # type: ignore[arg-type]
                # T3.82: this test's fixture markets do not carry 90 days of
                # candles, and the equivalence being proved (shard topology,
                # not the shadow-universe gate) is orthogonal to it.
                ShadowConfig(hot_state_tail=0, universe_min_history_days=0),
                ConsumerHealth(),
                shard_index=index,
                shard_total=total,
                clock=clock,
            )
        )
        for index, total in shards
    ]
    try:
        deadline = asyncio.get_event_loop().time() + DRAIN_TIMEOUT_S
        while len(sink) < expected:
            if asyncio.get_event_loop().time() > deadline:
                raise TimeoutError(f"only {len(sink)}/{expected} keys after {DRAIN_TIMEOUT_S}s")
            await asyncio.sleep(POLL_S)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass


class TestTwoShardsAgreeWithOneWorker:
    async def test_every_decision_is_byte_identical_and_evaluated_exactly_once(
        self,
        db_session_factory: Any,
        redis_client: Any,
        markets: list[Any],
        versions: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        expected_keys = len(markets) * versions

        # Published once: a brand-new consumer group starts at id="0" (module
        # docstring), so the two-shard groups below see these same entries
        # fresh, with no need (and no correctness reason) to republish them.
        await _publish_all(redis_client, markets)
        serial_sink: dict[tuple[str, str], list[Evaluation]] = {}
        monkeypatch.setattr(consumer_module, "evaluate_slot", _recording_evaluate_slot(serial_sink))
        await _drain(
            db_session_factory,
            redis_client,
            expected=expected_keys,
            shards=[(0, 1)],
            sink=serial_sink,
        )
        assert len(serial_sink) == expected_keys
        assert all(len(calls) == 1 for calls in serial_sink.values()), (
            "the unsharded baseline itself evaluated a bar more than once"
        )

        sharded_sink: dict[tuple[str, str], list[Evaluation]] = {}
        monkeypatch.setattr(
            consumer_module, "evaluate_slot", _recording_evaluate_slot(sharded_sink)
        )
        await _drain(
            db_session_factory,
            redis_client,
            expected=expected_keys,
            shards=[(i, SHARD_TOTAL) for i in range(SHARD_TOTAL)],
            sink=sharded_sink,
        )
        assert len(sharded_sink) == expected_keys
        assert all(len(calls) == 1 for calls in sharded_sink.values()), (
            "a bar was evaluated by more than one shard -- double processing"
        )

        assert set(serial_sink) == set(sharded_sink)
        for key, (before,) in serial_sink.items():
            (after,) = sharded_sink[key]
            assert after.state == before.state, key
            assert after.reason == before.reason, key
            assert after.decision == before.decision, key

        spike_symbol = markets[SPIKE_MARKET_INDEX].symbol
        triggered = [key for key in serial_sink if key[0] == spike_symbol]
        assert any(serial_sink[key][0].state.value == "triggered" for key in triggered), (
            "the one designed-to-trigger market produced no TRIGGERED evaluation at all"
        )
