"""The real Binance SPOT filters and fee schedule satisfy the adapter's protocols.

``hunter_core`` cannot *import* ``hunter_exchanges`` in production code — the
distribution dependency runs the other way — so :class:`SpotFilters` and
:class:`FeeSchedule` are structural. That leaves one honest risk: the shapes
drift apart and nothing notices until a worker wires them together.

This test closes it from the test side, where importing the sibling package is
free: it builds the real ``SpotMarketFilters`` from a recorded ``exchangeInfo``
shape and runs the paper adapter against it. Skipped, with a reason, when the
exchange package is not installed.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from hunter_core.execution.adapter import FeeSchedule, SpotFilters
from hunter_core.execution.entries import MarketEntryOrder
from hunter_core.execution.paper import PaperExecutionAdapter

from .conftest import DEEP_BOOK, NOW, approved_decision, seconds, trade

filters_module = pytest.importorskip(
    "hunter_exchanges.binance_spot.filters", reason="exchange adapters not installed"
)
fees_module = pytest.importorskip("hunter_exchanges.binance_spot.fees")

_RAW = {
    "symbol": "BTCUSDT",
    "filters": [
        {
            "filterType": "PRICE_FILTER",
            "tickSize": "0.01",
            "minPrice": "0.01",
            "maxPrice": "1000000",
        },
        {"filterType": "LOT_SIZE", "stepSize": "0.00001", "minQty": "0.00001", "maxQty": "9000"},
        {"filterType": "MARKET_LOT_SIZE", "stepSize": "0", "minQty": "0", "maxQty": "100"},
        {
            "filterType": "NOTIONAL",
            "minNotional": "5",
            "applyMinToMarket": True,
            "maxNotional": "9000000",
            "applyMaxToMarket": False,
            "avgPriceMins": 5,
        },
    ],
}


def test_the_real_filters_and_fee_schedule_satisfy_the_protocols() -> None:
    real_filters = filters_module.parse_filters(_RAW)
    assert isinstance(real_filters, SpotFilters)
    assert isinstance(fees_module.SPOT_VIP0, FeeSchedule)


def test_the_paper_adapter_fills_against_the_real_filter_object() -> None:
    """Not just "the shape matches": the adapter actually runs on it."""
    real_filters = filters_module.parse_filters(_RAW)
    order = MarketEntryOrder(
        decision=approved_decision(
            proposal_id=uuid.uuid4(),
            qty=str(Decimal("3")),
            entry_ref=str(Decimal("100")),
            stop=str(Decimal("95")),
        ),
        qty=Decimal("3"),
        decision_at=NOW - seconds(1),
    )
    report = PaperExecutionAdapter().submit_market_entry(
        order,
        DEEP_BOOK,
        trade("100"),
        real_filters,
        fees_module.SPOT_VIP0,
        NOW,
        avg_price=Decimal("100"),
    )
    assert report.status == "filled"
    assert report.fee is not None
    assert report.fee.rate == fees_module.SPOT_VIP0.taker_rate
    assert report.fee.source == fees_module.SPOT_VIP0.source


def test_the_real_notional_floor_refuses_the_lot_size_minimum() -> None:
    """Measured live in T3.0a §10: 0,00001 BTC ≈ 0,80 USDT, under the 5 USDT floor."""
    real_filters = filters_module.parse_filters(_RAW)
    order = MarketEntryOrder(
        decision=approved_decision(
            proposal_id=uuid.uuid4(),
            qty=str(Decimal("0.00001")),
            entry_ref=str(Decimal("100")),
            stop=str(Decimal("95")),
        ),
        qty=Decimal("0.00001"),
        decision_at=NOW - seconds(1),
    )
    report = PaperExecutionAdapter().submit_market_entry(
        order,
        DEEP_BOOK,
        trade("100"),
        real_filters,
        fees_module.SPOT_VIP0,
        NOW,
        avg_price=Decimal("100"),
    )
    assert (report.status, report.reason) == ("rejected", "min_notional")
