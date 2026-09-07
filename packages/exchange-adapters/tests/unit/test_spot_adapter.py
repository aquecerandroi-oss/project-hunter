"""BinanceSpotAdapter: the Protocol, the identity, the fees.

The identity tests are the point of T3.0a: the same string ``BTCUSDT`` must
never mean the same market on the spot adapter and on the USDS-M one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import MarketType
from hunter_exchanges.base import ExchangeAdapter, ExchangeError, StreamChannel
from hunter_exchanges.binance import BinanceAdapter
from hunter_exchanges.binance_spot import BinanceSpotAdapter
from hunter_exchanges.binance_spot.fees import SPOT_VIP0, SPOT_VIP0_BNB, fee_for
from hunter_exchanges.binance_spot.identity import MarketTyped, market_identity

pytestmark = pytest.mark.unit


class _StubRest:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def fetch_ticker(self, symbol: str) -> Any:
        self.calls.append(("fetch_ticker", symbol))
        return None

    async def fetch_avg_price(self, symbol: str) -> Any:
        self.calls.append(("fetch_avg_price", symbol))
        return None

    def rest_gate_status(self) -> str:
        return "ok"

    async def aclose(self) -> None:
        pass


class _StubWs:
    def __init__(self) -> None:
        self.updates: list[tuple[Any, ...]] = []
        self.out_of_sequence_count = 0

    async def update_subscriptions(self, added: Any, removed: Any, channels: Any) -> None:
        self.updates.append((added, removed, channels))

    def connection_state(self) -> str:
        return "disconnected"

    def connection_states(self) -> dict[str, Any]:
        return {}

    async def aclose(self) -> None:
        pass


def _adapter() -> BinanceSpotAdapter:
    return BinanceSpotAdapter(rest=_StubRest(), ws=_StubWs())  # type: ignore[arg-type]


def test_the_spot_adapter_satisfies_the_exchange_adapter_protocol() -> None:
    assert isinstance(BinanceSpotAdapter(), ExchangeAdapter)


def test_both_adapters_declare_their_market_type() -> None:
    """Neither is inferred: a wrong default would silently label a spot pair
    as a perpetual."""
    spot = BinanceSpotAdapter()
    perp = BinanceAdapter()

    assert isinstance(spot, MarketTyped)
    assert isinstance(perp, MarketTyped)
    assert spot.market_type is MarketType.SPOT
    assert perp.market_type is MarketType.PERPETUAL


def test_the_same_symbol_is_two_different_markets() -> None:
    spot = BinanceSpotAdapter()
    perp = BinanceAdapter()

    assert spot.code == perp.code == "binance"  # one venue, one exchanges row
    assert spot.identity("BTCUSDT") == "binance:spot:BTCUSDT"
    assert spot.identity("BTCUSDT") != market_identity(perp.code, "BTCUSDT", perp.market_type)


def test_market_identity_never_collapses_to_exchange_and_symbol() -> None:
    spot_key = market_identity("binance", "BTCUSDT", MarketType.SPOT)
    perp_key = market_identity("binance", "BTCUSDT", MarketType.PERPETUAL)

    assert spot_key != perp_key
    assert MarketType.SPOT.value in spot_key
    assert MarketType.PERPETUAL.value in perp_key


async def test_funding_and_open_interest_are_refused_not_faked() -> None:
    adapter = _adapter()

    with pytest.raises(ExchangeError) as funding:
        await adapter.fetch_funding("BTCUSDT")
    with pytest.raises(ExchangeError) as oi:
        await adapter.fetch_open_interest("BTCUSDT")

    assert funding.value.retryable is False
    assert oi.value.retryable is False


async def test_calls_delegate_to_the_rest_and_ws_clients() -> None:
    rest = _StubRest()
    ws = _StubWs()
    adapter = BinanceSpotAdapter(rest=rest, ws=ws)  # type: ignore[arg-type]

    await adapter.fetch_ticker("BTCUSDT")
    await adapter.fetch_avg_price("BTCUSDT")
    await adapter.update_subscriptions(["SOLUSDT"], ["ETHUSDT"], [StreamChannel.TRADES])

    assert rest.calls == [("fetch_ticker", "BTCUSDT"), ("fetch_avg_price", "BTCUSDT")]
    assert ws.updates == [(["SOLUSDT"], ["ETHUSDT"], [StreamChannel.TRADES])]


def test_spot_fees_are_the_spot_ones_with_their_source() -> None:
    """0.1%/0.1% at VIP 0, no BNB deduction assumed - and explicitly not the
    USDS-M schedule (0.02%/0.05%), which would understate every cost."""
    adapter = BinanceSpotAdapter()

    assert adapter.fees is SPOT_VIP0
    assert adapter.fees.taker_rate == Decimal("0.001")
    assert adapter.fees.maker_rate == Decimal("0.001")
    assert adapter.fees.bnb_deduction is False
    assert adapter.fees.taker_bps == Decimal("10")
    assert "VIP 0" in adapter.fees.source
    assert adapter.fees.as_of == datetime(2026, 9, 6, tzinfo=UTC).date()


def test_the_bnb_discount_exists_but_is_never_the_default() -> None:
    assert SPOT_VIP0_BNB.taker_rate == Decimal("0.00075")
    assert SPOT_VIP0_BNB.bnb_deduction is True
    assert BinanceSpotAdapter.fees is not SPOT_VIP0_BNB


def test_fee_for_a_notional_is_rounded_against_us() -> None:
    assert fee_for(Decimal("1000")) == Decimal("1.00000000")
    assert fee_for(Decimal("1000"), schedule=SPOT_VIP0_BNB) == Decimal("0.75000000")
    # A cost never rounds in our favour: 1e-9 becomes the smallest unit, not 0.
    assert fee_for(Decimal("0.000001")) == Decimal("0.00000001")

    with pytest.raises(ValueError, match="liquidity"):
        fee_for(Decimal("1000"), liquidity="rebate")
