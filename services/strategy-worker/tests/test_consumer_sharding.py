"""``run_consumer`` refuses a bar for a market it does not own (T3.74f).

Same fake-``consume()`` pattern as ``test_reclaim_dedup.py``: a scripted
stream, no Docker, no real Redis -- what is under test is the loop's own
ownership check, which must run *before* the dispatcher (and therefore
before ``handle_candle``) ever sees the message.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from hunter_core.events.envelope import EventEnvelope
from hunter_core.observability import registry
from hunter_strategy_worker import consumer as consumer_mod
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.consumer import ConsumerHealth, run_consumer

pytestmark = pytest.mark.unit


class _Runtime:
    def __init__(self) -> None:
        self.instance = "test:1"
        self.errors = 0
        self.successes = 0

    def mark_error(self) -> None:
        self.errors += 1

    def mark_success(self) -> None:
        self.successes += 1


def _envelope(symbol: str) -> EventEnvelope:
    return EventEnvelope(
        type="market.candles.closed",
        producer="test",
        key=symbol,
        payload={"exchange": "binance", "symbol": symbol, "market_type": "perpetual"},
    )


def _skipped(reason: str) -> float:
    value = registry.get_sample_value("hunter_shadow_bars_skipped_total", {"reason": reason})
    return 0.0 if value is None else value


async def _drive(
    monkeypatch: pytest.MonkeyPatch, entries: list[tuple[str, EventEnvelope]], **shard_kwargs: int
) -> tuple[list[str], list[str]]:
    handled: list[str] = []
    acked: list[str] = []

    async def stream(*_a: Any, **_kw: Any) -> AsyncIterator[tuple[str, EventEnvelope]]:
        for item in entries:
            yield item

    async def fake_handle_candle(*_a: Any, payload: dict[str, Any], **_kw: Any) -> None:
        handled.append(payload["symbol"])

    async def fake_ack(
        _redis: Any, _stream: Any, _group: Any, message_id: str, _envelope: Any
    ) -> None:
        acked.append(message_id)

    async def fake_sleep(_delay: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(consumer_mod, "consume", stream)
    monkeypatch.setattr(consumer_mod, "handle_candle", fake_handle_candle)
    monkeypatch.setattr(consumer_mod, "ack", fake_ack)
    monkeypatch.setattr(consumer_mod.asyncio, "sleep", fake_sleep)

    runtime, health = _Runtime(), ConsumerHealth()
    # T3.82: the shadow-universe gate is out of scope here (shard ownership
    # only) and would otherwise refuse every bar -- a query against a real
    # database with `factory=None` -- so it is disabled for this test.
    config = ShadowConfig(universe_min_history_days=0)
    with pytest.raises(asyncio.CancelledError):
        await run_consumer(None, None, runtime, config, health, **shard_kwargs)  # type: ignore[arg-type]
    return handled, acked


class TestOwnershipRefusal:
    async def test_a_bar_for_a_market_this_shard_does_not_own_is_acked_and_never_evaluated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ETHUSDT and BTCUSDT do not share a crc32%2 slice -- picked by running
        # the formula once, not asserted here (that belongs to test_shard.py).
        entries = [("1-1", _envelope("ETHUSDT")), ("1-2", _envelope("BTCUSDT"))]
        before_not_mine = _skipped("not_my_shard")
        handled, acked = await _drive(monkeypatch, entries, shard_index=0, shard_total=2)

        owned = [s for s in ("ETHUSDT", "BTCUSDT") if s in handled]
        skipped = [s for s in ("ETHUSDT", "BTCUSDT") if s not in handled]
        assert len(owned) == 1, "exactly one of the two symbols must be owned by shard 0 of 2"
        assert len(skipped) == 1
        # Every entry is acked either way -- owned ones by the normal handler
        # path, skipped ones by the ownership refusal itself.
        assert sorted(acked) == ["1-1", "1-2"]
        assert _skipped("not_my_shard") == before_not_mine + 1

    async def test_solo_deployment_owns_everything(self, monkeypatch: pytest.MonkeyPatch) -> None:
        entries = [("1-1", _envelope("ETHUSDT")), ("1-2", _envelope("BTCUSDT"))]
        handled, acked = await _drive(monkeypatch, entries)  # shard_index=0, shard_total=1 defaults
        assert handled == ["ETHUSDT", "BTCUSDT"]
        assert acked == ["1-1", "1-2"]

    async def test_both_shards_of_a_topology_together_cover_every_symbol_exactly_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        symbols = [f"SYM{i}USDT" for i in range(20)]
        entries = [(f"1-{i}", _envelope(s)) for i, s in enumerate(symbols)]
        handled_by_shard: list[list[str]] = []
        for shard_index in range(4):
            handled, _ = await _drive(monkeypatch, entries, shard_index=shard_index, shard_total=4)
            handled_by_shard.append(handled)
        seen: set[str] = set()
        for handled in handled_by_shard:
            assert seen.isdisjoint(handled), "a symbol was handled by more than one shard"
            seen.update(handled)
        assert seen == set(symbols)
