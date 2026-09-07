"""hunter_exchanges.binance_spot.filters: the filters a MARKET order must pass.

The reference payload is the recorded ``spot_exchange_info.json`` (BTCUSDT),
so ``LOT_SIZE``/``MARKET_LOT_SIZE``/``NOTIONAL``/``PRICE_FILTER``/
``PERCENT_PRICE_BY_SIDE`` are exercised exactly as Binance publishes them.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_core.domain.enums import OrderSide
from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.binance_spot import filters as flt

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).parents[1] / ".." / "hunter_exchanges" / "testing" / "fixtures"
).resolve()


def _btcusdt_entry() -> dict[str, Any]:
    raw = json.loads((FIXTURES / "spot_exchange_info.json").read_text(encoding="utf-8"))
    return next(s for s in raw["symbols"] if s["symbol"] == "BTCUSDT")


@pytest.fixture
def btcusdt() -> flt.SpotMarketFilters:
    return flt.parse_filters(_btcusdt_entry())


def test_parse_filters_reads_every_market_relevant_filter(btcusdt: flt.SpotMarketFilters) -> None:
    assert btcusdt.symbol == "BTCUSDT"
    assert btcusdt.tick_size == Decimal("0.01000000")
    assert btcusdt.min_price == Decimal("0.01000000")
    assert btcusdt.step_size == Decimal("0.00001000")
    assert btcusdt.min_qty == Decimal("0.00001000")
    assert btcusdt.max_qty == Decimal("9000.00000000")
    # MARKET_LOT_SIZE on BTCUSDT: no step of its own (0 = not enforced), but
    # a real maxQty that LOT_SIZE alone does not express.
    assert btcusdt.market_step_size == Decimal("0")
    assert btcusdt.market_max_qty == Decimal("112.97976583")
    assert btcusdt.min_notional == Decimal("5.00000000")
    assert btcusdt.apply_min_to_market is True
    assert btcusdt.max_notional == Decimal("9000000.00000000")
    assert btcusdt.apply_max_to_market is False
    assert btcusdt.avg_price_mins == 5
    assert btcusdt.ask_multiplier_up == Decimal("2")
    assert btcusdt.bid_multiplier_down == Decimal("0.5")


def test_parse_filters_accepts_the_legacy_min_notional_filter() -> None:
    """Older/other symbols still publish ``MIN_NOTIONAL`` with
    ``applyToMarket`` instead of ``NOTIONAL``/``applyMinToMarket``."""
    entry = {
        "symbol": "OLDUSDT",
        "filters": [
            {"filterType": "PRICE_FILTER", "minPrice": "0.1", "maxPrice": "100", "tickSize": "0.1"},
            {"filterType": "LOT_SIZE", "minQty": "1", "maxQty": "100", "stepSize": "1"},
            {
                "filterType": "MIN_NOTIONAL",
                "minNotional": "10",
                "applyToMarket": True,
                "avgPriceMins": 5,
            },
        ],
    }

    parsed = flt.parse_filters(entry)

    assert parsed.min_notional == Decimal("10")
    assert parsed.apply_min_to_market is True
    assert parsed.avg_price_mins == 5


def test_parse_filters_rejects_a_symbol_without_lot_size() -> None:
    with pytest.raises(MalformedMessage):
        flt.parse_filters({"symbol": "XUSDT", "filters": []})


def test_round_qty_down_never_rounds_up(btcusdt: flt.SpotMarketFilters) -> None:
    """A rounded-up quantity is an order the exchange rejects (or a bigger
    position than the Risk Engine approved) - always floor to the step."""
    assert btcusdt.round_qty_down(Decimal("0.001239")) == Decimal("0.00123")
    assert btcusdt.round_qty_down(Decimal("0.00001")) == Decimal("0.00001")
    assert btcusdt.round_qty_down(Decimal("0.000009")) == Decimal("0")


def test_round_qty_down_applies_the_coarser_market_lot_step() -> None:
    parsed = flt.parse_filters(
        {
            "symbol": "XUSDT",
            "filters": [
                {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "100", "stepSize": "0.001"},
                {
                    "filterType": "MARKET_LOT_SIZE",
                    "minQty": "0.1",
                    "maxQty": "50",
                    "stepSize": "0.1",
                },
            ],
        }
    )

    assert parsed.round_qty_down(Decimal("1.234")) == Decimal("1.2")


def test_round_price_rounds_to_the_tick_against_us(btcusdt: flt.SpotMarketFilters) -> None:
    """Never in our favour: a buy pays the higher tick, a sell receives the
    lower one - the same rule the paper fill must use to stay honest."""
    assert btcusdt.round_price(Decimal("80488.011"), side=OrderSide.BUY) == Decimal("80488.02")
    assert btcusdt.round_price(Decimal("80488.019"), side=OrderSide.SELL) == Decimal("80488.01")


def test_check_market_order_accepts_a_normal_size(btcusdt: flt.SpotMarketFilters) -> None:
    check = btcusdt.check_market_order(Decimal("0.0012345"), avg_price=Decimal("80471.72575004"))

    assert check.ok is True
    assert check.reason is None
    assert check.qty == Decimal("0.00123")  # floored to stepSize
    assert check.notional == Decimal("0.00123") * Decimal("80471.72575004")


def test_check_market_order_refuses_below_min_notional_using_avg_price(
    btcusdt: flt.SpotMarketFilters,
) -> None:
    """``NOTIONAL.applyMinToMarket`` is true with ``avgPriceMins=5``: the
    reference price for a MARKET order is ``/api/v3/avgPrice``, never the
    last trade - 0.00005 BTC x ~80471 = ~4.02 USDT, under the 5 USDT floor.
    """
    check = btcusdt.check_market_order(Decimal("0.00005"), avg_price=Decimal("80471.72575004"))

    assert check.ok is False
    assert check.reason == "min_notional"
    assert check.qty == Decimal("0.00005")


def test_check_market_order_refuses_below_min_qty(btcusdt: flt.SpotMarketFilters) -> None:
    check = btcusdt.check_market_order(Decimal("0.000009"), avg_price=Decimal("80471.72"))

    assert check.ok is False
    assert check.reason == "min_qty"
    assert check.qty == Decimal("0")


def test_check_market_order_refuses_over_the_market_lot_max(
    btcusdt: flt.SpotMarketFilters,
) -> None:
    check = btcusdt.check_market_order(Decimal("200"), avg_price=Decimal("80471.72"))

    assert check.ok is False
    assert check.reason == "max_qty"


def test_check_market_order_refuses_when_avg_price_is_unavailable(
    btcusdt: flt.SpotMarketFilters,
) -> None:
    """No reference price means no honest notional check: refuse, never
    substitute the last trade for the average the filter names."""
    check = btcusdt.check_market_order(Decimal("0.01"), avg_price=None)

    assert check.ok is False
    assert check.reason == "avg_price_unavailable"
    assert check.notional is None


def test_check_market_order_uses_last_price_when_avg_price_mins_is_zero() -> None:
    parsed = flt.parse_filters(
        {
            "symbol": "XUSDT",
            "filters": [
                {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "100", "stepSize": "0.001"},
                {
                    "filterType": "NOTIONAL",
                    "minNotional": "10",
                    "applyMinToMarket": True,
                    "maxNotional": "1000000",
                    "applyMaxToMarket": False,
                    "avgPriceMins": 0,
                },
            ],
        }
    )

    check = parsed.check_market_order(Decimal("1"), avg_price=None, last_price=Decimal("20"))

    assert check.ok is True
    assert check.notional == Decimal("20")


def test_check_market_order_ignores_max_notional_when_it_is_not_applied_to_market(
    btcusdt: flt.SpotMarketFilters,
) -> None:
    """``applyMaxToMarket`` is false on BTCUSDT: a notional over maxNotional
    is not a MARKET rejection (the exchange only applies it to limit orders).
    """
    check = btcusdt.check_market_order(Decimal("112"), avg_price=Decimal("80471.72575004"))

    assert check.notional is not None and check.notional > btcusdt.max_notional  # type: ignore[operator]
    assert check.ok is True


def test_price_band_is_our_own_sanity_guard_not_an_exchange_market_rule(
    btcusdt: flt.SpotMarketFilters,
) -> None:
    """``PERCENT_PRICE_BY_SIDE`` bounds a *limit* price on Binance; we keep
    the band to sanity-check a simulated MARKET fill that walked the book,
    and it is labelled as ours - the exchange never rejects a MARKET order
    for it."""
    low, high = btcusdt.price_band(OrderSide.BUY, avg_price=Decimal("80000"))

    # BUY reads the bid multipliers (0.5 / 1.2), SELL the ask ones (0.8 / 2).
    assert (low, high) == (Decimal("40000.0"), Decimal("96000.0"))
    assert btcusdt.price_band(OrderSide.SELL, avg_price=Decimal("80000")) == (
        Decimal("64000.0"),
        Decimal("160000"),
    )
