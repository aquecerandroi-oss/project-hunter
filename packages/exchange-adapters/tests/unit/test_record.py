"""hunter_exchanges.testing.record: the exchange_info symbol-selection logic.

``record.py`` itself is a network script (never imported by pytest, per its
own docstring) — this only exercises the pure, offline
:func:`select_exchange_info_symbols` helper (F15).
"""

from __future__ import annotations

from typing import Any

import pytest

from hunter_exchanges.testing.record import TRIM_SYMBOLS, select_exchange_info_symbols

pytestmark = pytest.mark.unit


def _symbol(
    symbol: str, *, quote: str = "USDT", contract: str = "PERPETUAL", status: str = "TRADING"
) -> dict[str, Any]:
    return {"symbol": symbol, "quoteAsset": quote, "contractType": contract, "status": status}


def test_select_exchange_info_symbols_keeps_trim_symbols_usdt_perpetuals() -> None:
    symbols = [_symbol(f"SYM{i}USDT") for i in range(10)]

    selected = select_exchange_info_symbols(symbols)

    assert len(selected) == TRIM_SYMBOLS
    assert [s["symbol"] for s in selected] == [f"SYM{i}USDT" for i in range(TRIM_SYMBOLS)]


def test_select_exchange_info_symbols_keeps_a_settling_row_past_the_trim() -> None:
    """F15: re-running the recorder must not silently drop the SETTLING row
    ``test_parse_exchange_info*`` depends on, even though it is far past the
    first ``TRIM_SYMBOLS`` USDT perpetuals in listing order."""
    symbols = [_symbol(f"SYM{i}USDT") for i in range(10)]
    symbols.append(_symbol("OMGUSDT", status="SETTLING"))

    selected = select_exchange_info_symbols(symbols)

    assert "OMGUSDT" in {s["symbol"] for s in selected}
    assert len(selected) == TRIM_SYMBOLS + 1


def test_select_exchange_info_symbols_keeps_a_non_usdt_quote_row() -> None:
    symbols = [_symbol(f"SYM{i}USDT") for i in range(10)]
    symbols.append(_symbol("ETHBTC", quote="BTC"))

    selected = select_exchange_info_symbols(symbols)

    assert "ETHBTC" in {s["symbol"] for s in selected}


def test_select_exchange_info_symbols_keeps_a_quarterly_future_row() -> None:
    symbols = [_symbol(f"SYM{i}USDT") for i in range(10)]
    symbols.append(_symbol("BTCUSDT_260925", contract="CURRENT_QUARTER"))

    selected = select_exchange_info_symbols(symbols)

    assert "BTCUSDT_260925" in {s["symbol"] for s in selected}


def test_select_exchange_info_symbols_keeps_every_edge_case_together() -> None:
    """The real fixture (``exchange_info.json``) carries all three edge
    cases plus 5 USDT perpetuals — 8 rows total."""
    symbols = [_symbol(f"SYM{i}USDT") for i in range(TRIM_SYMBOLS)]
    symbols.append(_symbol("OMGUSDT", status="SETTLING"))
    symbols.append(_symbol("ETHBTC", quote="BTC"))
    symbols.append(_symbol("BTCUSDT_260925", contract="CURRENT_QUARTER"))

    selected = select_exchange_info_symbols(symbols)

    assert len(selected) == TRIM_SYMBOLS + 3


def test_select_exchange_info_symbols_never_duplicates_a_row_matching_two_edge_cases() -> None:
    """A single row can satisfy more than one edge-case predicate at once
    (e.g. a non-USDT-quote *and* non-perpetual contract) — it must be kept
    once, not appended twice."""
    symbols = [_symbol(f"SYM{i}USDT") for i in range(TRIM_SYMBOLS)]
    symbols.append(_symbol("ETHBTC_260925", quote="BTC", contract="CURRENT_QUARTER"))

    selected = select_exchange_info_symbols(symbols)

    names = [s["symbol"] for s in selected]
    assert names.count("ETHBTC_260925") == 1
