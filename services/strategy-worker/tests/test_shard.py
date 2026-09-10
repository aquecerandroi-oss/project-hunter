"""``owns_market`` (T3.74f) -- pure function, no Docker required.

Mirrors ``services/market-worker/tests/test_universe_sharding.py``'s shape
(same synthetic universe idea) plus a direct cross-check against
``hunter_market_worker.shard_symbols``: the whole point of
``hunter_core.sharding`` is that a symbol lands on the same shard index in
both services.
"""

from __future__ import annotations

import pytest

from hunter_market_worker.universe import shard_symbols
from hunter_strategy_worker.shard import owns_market

pytestmark = pytest.mark.unit

_MAJORS = [
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK",
    "MATIC", "LTC", "TRX", "BCH", "NEAR", "UNI", "ATOM", "ETC", "XLM", "FIL",
]  # fmt: skip


def _universe(size: int = 200) -> list[str]:
    symbols = [f"{base}USDT" for base in _MAJORS]
    tail = 0
    while len(symbols) < size:
        symbols.append(f"ALT{tail:04d}USDT")
        tail += 1
    return symbols[:size]


@pytest.mark.parametrize("shard_total", [1, 2, 3, 4])
def test_every_symbol_owned_by_exactly_one_shard(shard_total: int) -> None:
    universe = _universe()
    owners = [
        [symbol for symbol in universe if owns_market(symbol, i, shard_total)]
        for i in range(shard_total)
    ]
    seen: set[str] = set()
    for owned in owners:
        assert seen.isdisjoint(owned), "a symbol was owned by more than one shard"
        seen.update(owned)
    assert seen == set(universe), "the union of every shard must be the whole universe"


def test_shard_total_one_owns_every_symbol() -> None:
    for symbol in _universe():
        assert owns_market(symbol, 0, 1) is True


def test_shard_index_out_of_range_owns_nothing() -> None:
    for symbol in _universe():
        assert owns_market(symbol, 5, 4) is False


@pytest.mark.parametrize("shard_total", [1, 2, 3, 4])
def test_agrees_with_the_market_worker_shard_function(shard_total: int) -> None:
    """T3.74f's own reason to exist: the strategy-worker must shard a symbol
    to the *same* index the market-worker already uses for it, without
    importing the market-worker's code -- proven here by importing it
    anyway, in the one place (a test) allowed to check the two never drift."""
    universe = _universe()
    for shard_index in range(shard_total):
        expected = set(shard_symbols(universe, shard_index, shard_total))
        actual = {s for s in universe if owns_market(s, shard_index, shard_total)}
        assert actual == expected


_REAL_NON_ASCII = ["牛来USDT", "龙虾USDT", "币安人生USDT", "我踏马来了USDT"]


def test_non_ascii_symbols_do_not_raise() -> None:
    for symbol in _universe(20) + _REAL_NON_ASCII:
        owns_market(symbol, 1, 4)  # must not raise
