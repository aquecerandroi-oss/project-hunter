"""BinanceAdapter: composes rest/ws behind ExchangeAdapter + ExchangeAdapterExtras."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from hunter_exchanges.base import ExchangeAdapter, ExchangeAdapterExtras, StreamChannel
from hunter_exchanges.binance import BinanceAdapter

pytestmark = pytest.mark.unit


class _StubRest:
    def __init__(self) -> None:
        self.realized_funding_calls: list[tuple[Any, ...]] = []
        self.server_time_called = False

    async def fetch_realized_funding(
        self, symbol: str, start: datetime, end: datetime | None = None, *, limit: int = 1000
    ) -> list[Any]:
        self.realized_funding_calls.append((symbol, start, end, limit))
        return []

    async def server_time(self) -> datetime:
        self.server_time_called = True
        return datetime(2026, 1, 1, tzinfo=UTC)

    async def aclose(self) -> None:
        pass


class _StubWs:
    def __init__(self) -> None:
        self.update_calls: list[tuple[Any, ...]] = []

    async def update_subscriptions(self, added: Any, removed: Any, channels: Any) -> None:
        self.update_calls.append((added, removed, channels))

    def connection_states(self) -> dict[str, Any]:
        return {}

    def connection_state(self) -> str:
        return "disconnected"

    async def aclose(self) -> None:
        pass


def test_binance_adapter_satisfies_both_protocols() -> None:
    adapter = BinanceAdapter()
    assert isinstance(adapter, ExchangeAdapter)
    assert isinstance(adapter, ExchangeAdapterExtras)


async def test_fetch_realized_funding_delegates_to_rest() -> None:
    rest = _StubRest()
    adapter = BinanceAdapter(rest=rest, ws=_StubWs())  # type: ignore[arg-type]

    await adapter.fetch_realized_funding("BTCUSDT", datetime(2026, 1, 1, tzinfo=UTC))

    assert rest.realized_funding_calls == [
        ("BTCUSDT", datetime(2026, 1, 1, tzinfo=UTC), None, 1000)
    ]


async def test_update_subscriptions_delegates_to_ws() -> None:
    ws = _StubWs()
    adapter = BinanceAdapter(rest=_StubRest(), ws=ws)  # type: ignore[arg-type]

    await adapter.update_subscriptions(["BTCUSDT"], ["ETHUSDT"], [StreamChannel.TRADES])

    assert ws.update_calls == [(["BTCUSDT"], ["ETHUSDT"], [StreamChannel.TRADES])]
