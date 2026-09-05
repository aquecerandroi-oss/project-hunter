"""hunter_exchanges.symbols: internal symbol conventions."""

from __future__ import annotations

import pytest

from hunter_exchanges.symbols import internal_symbol, split_base_quote

pytestmark = pytest.mark.unit


def test_binance_symbol_is_already_internal_form() -> None:
    assert internal_symbol("BTCUSDT") == "BTCUSDT"


@pytest.mark.parametrize("raw", ["BTC-USDT", "BTC_USDT", "BTC/USDT", "btcusdt"])
def test_separators_are_stripped_and_upper_cased(raw: str) -> None:
    assert internal_symbol(raw) == "BTCUSDT"


def test_split_base_quote_trusts_exchange_info_fields() -> None:
    assert split_base_quote("btc", "usdt") == ("BTC", "USDT")
