"""T3.82, against a real stream and Postgres: the shadow universe in practice.

Three markets: two with >= 90 days of final 1m candles, one with ~1.1 days.
Publishing one ``market.candles.closed`` bar per market and draining through
``run_consumer`` (the real gate, ``ShadowConfig``'s default 90 days) must
produce decisions only for the two old markets, ack the young one without
persisting a row, and count it under ``reason="universe_history"``.

**The byte-identical proof, reusing ``test_dispatch_benchmark.py``'s
technique.** The same three bars are also delivered once through
``handle_candle`` directly (concurrency 1, no gate -- ``handle_candle`` never
consults the universe; only ``run_consumer``/``pre_dispatch`` does) to record
every real :class:`~hunter_core.strategies.base.Evaluation`. The gated run's
decisions for the two old markets must be byte-identical (state, reason,
decision) to that baseline -- the gate changes *which* markets decide, never
*what* an admitted one decides.
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
from hunter_core.observability import registry
from hunter_core.strategies.base import Evaluation
from hunter_strategy_worker import consumer as consumer_module
from hunter_strategy_worker.catalogue import ActiveVersion, load_active_versions
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.consumer import ConsumerHealth, handle_candle, run_consumer
from hunter_strategy_worker.decide import evaluate_slot as real_evaluate_slot
from hunter_strategy_worker.repo import load_market

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

LATE = datetime(2026, 9, 10, 13, 0, tzinfo=UTC)
OLD_HISTORY_DAYS = 91
"""One day past the 90-day default -- comfortably on the eligible side of the
inclusive boundary (``test_universe.py`` covers the boundary itself)."""
POLL_S = 0.05
DRAIN_TIMEOUT_S = 20.0

SYMBOLS = {"old_a": "UGATEOLDAUSDT", "old_b": "UGATEOLDBUSDT", "young": "UGATEYOUNGUSDT"}


class _Runtime:
    def __init__(self) -> None:
        self.instance = "test:universe-gate"

    def mark_error(self) -> None:
        pass

    def mark_success(self) -> None:
        pass


def _recording_evaluate_slot(sink: dict[tuple[str, str], Evaluation]) -> Any:
    async def wrapper(*args: Any, market: Any, version: ActiveVersion, **kwargs: Any) -> Evaluation:
        evaluation = await real_evaluate_slot(*args, market=market, version=version, **kwargs)
        sink[(market.symbol, version.version)] = evaluation
        return evaluation

    return wrapper


def _skipped(reason: str) -> float:
    value = registry.get_sample_value("hunter_shadow_bars_skipped_total", {"reason": reason})
    return 0.0 if value is None else value


@pytest.fixture
async def markets(db_session_factory: Any) -> dict[str, Any]:
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, LATE)
        await ensure_partitions(owner, LATE - timedelta(days=OLD_HISTORY_DAYS + 5))
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(text("DELETE FROM shadow_outbox"))
        await session.execute(text("DELETE FROM shadow_episodes"))
        await session.execute(text("DELETE FROM signal_outcomes"))
        await session.execute(text("DELETE FROM agent_signals"))
        await session.execute(text("DELETE FROM candles"))
        for label, symbol in SYMBOLS.items():
            _exchange_id, market_id = await seed_market(session, symbol=symbol, base_asset="BTC")
            await insert_candles(session, market_id, series(LATE, trigger=False))
            if label != "young":
                # The one row that decides membership: MIN(open_time) over
                # the market's final 1m candles. The recent series above
                # already gives the strategy real context to read; this row
                # alone pushes that minimum past the 90-day line.
                anchor_open = LATE - timedelta(days=OLD_HISTORY_DAYS)
                await insert_candles(
                    session,
                    market_id,
                    [
                        {
                            "open_time": anchor_open,
                            "open": Decimal("100"),
                            "high": Decimal("100.1"),
                            "low": Decimal("99.9"),
                            "close": Decimal("100"),
                            "volume": Decimal("10"),
                        }
                    ],
                )
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = {
            label: await load_market(session, EXCHANGE, symbol) for label, symbol in SYMBOLS.items()
        }
    assert all(row is not None for row in rows.values())
    return rows


@pytest.fixture
async def versions(db_session_factory: Any) -> int:
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await activate_version(session, key="universe_gate_family", version="v1")
        await isolate_catalogue(session, keep="universe_gate_family")
    return 1


def _payload(market: Any) -> dict[str, Any]:
    return to_wire(
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


class _Versions:
    def __init__(self, versions_list: list[ActiveVersion]) -> None:
        self._versions = versions_list

    async def get(self, _factory: Any) -> list[ActiveVersion]:
        return list(self._versions)


class TestShadowUniverseGate:
    async def test_only_markets_with_ninety_days_of_history_decide(
        self,
        db_session_factory: Any,
        redis_client: Any,
        markets: dict[str, Any],
        versions: int,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        del versions
        clock = lambda: LATE + timedelta(seconds=2)  # noqa: E731

        # --- baseline: the same three bars, straight through handle_candle,
        # which never consults the universe at all. ---
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            active = await load_active_versions(session)
        version_family = [v for v in active if v.strategy_key == "universe_gate_family"]
        assert len(version_family) == 1

        baseline_sink: dict[tuple[str, str], Evaluation] = {}
        monkeypatch.setattr(
            consumer_module, "evaluate_slot", _recording_evaluate_slot(baseline_sink)
        )
        health = ConsumerHealth()
        for market in markets.values():
            await handle_candle(
                db_session_factory,
                redis_client,
                payload=_payload(market),
                versions=_Versions(version_family),  # type: ignore[arg-type]
                config=ShadowConfig(hot_state_tail=0),
                health=health,
                clock=clock,
            )
        assert len(baseline_sink) == 3, "the baseline itself must decide on all three markets"

        # --- the real gate: publish to the real stream, drain through
        # run_consumer with the default (90-day) universe enabled. ---
        for market in markets.values():
            envelope = EventEnvelope(
                type="market.candles.closed",
                producer="test",
                key=f"{market.exchange}:{market.symbol}",
                payload=_payload(market),
            )
            await publish(redis_client, Streams.MARKET_CANDLES_CLOSED, envelope, maxlen=10_000)

        gated_sink: dict[tuple[str, str], Evaluation] = {}
        monkeypatch.setattr(consumer_module, "evaluate_slot", _recording_evaluate_slot(gated_sink))
        before_skipped = _skipped("universe_history")

        task = asyncio.ensure_future(
            run_consumer(
                db_session_factory,
                redis_client,
                _Runtime(),  # type: ignore[arg-type]
                ShadowConfig(hot_state_tail=0),
                ConsumerHealth(),
                clock=clock,
            )
        )
        try:
            deadline = asyncio.get_event_loop().time() + DRAIN_TIMEOUT_S
            while len(gated_sink) < 2:
                if asyncio.get_event_loop().time() > deadline:
                    raise TimeoutError(f"only {len(gated_sink)}/2 keys after {DRAIN_TIMEOUT_S}s")
                await asyncio.sleep(POLL_S)
            # One extra beat: proves the young market's bar was drained (and
            # refused) too, not merely that we stopped watching too early.
            await asyncio.sleep(0.2)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        gated_symbols = {symbol for symbol, _version in gated_sink}
        assert gated_symbols == {markets["old_a"].symbol, markets["old_b"].symbol}, (
            "the young market must never reach evaluate_slot"
        )
        assert _skipped("universe_history") == before_skipped + 1

        for label in ("old_a", "old_b"):
            key = (markets[label].symbol, version_family[0].version)
            gated = gated_sink[key]
            base = baseline_sink[key]
            assert gated.state == base.state, key
            assert gated.reason == base.reason, key
            assert gated.decision == base.decision, key

        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            young_signals = await session.scalar(
                text("SELECT count(*) FROM agent_signals WHERE market_id = :id"),
                {"id": markets["young"].id},
            )
        assert young_signals == 0, "a refused bar must never persist a decision"
