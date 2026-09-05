"""``shard_symbols`` (T1.6b-C2) â€” pure function, no Docker required.

Uses a synthetic 200-symbol universe shaped like Binance's real perpetual
list (a handful of high-volume majors plus a long tail, all ``*USDT``) since
this module must not depend on a live exchange or on
``packages/exchange-adapters`` fixtures owned by another agent this wave.
"""

from __future__ import annotations

import pytest

from hunter_market_worker.universe import shard_symbols

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
def test_every_symbol_lands_on_exactly_one_shard(shard_total: int) -> None:
    universe = _universe()
    seen: set[str] = set()
    for shard_index in range(shard_total):
        shard = shard_symbols(universe, shard_index, shard_total)
        assert seen.isdisjoint(shard), "a symbol was assigned to more than one shard"
        seen.update(shard)
    assert seen == set(universe), "the union of every shard must be the whole universe"


def test_shard_total_one_yields_the_whole_universe_unchanged() -> None:
    universe = _universe()
    assert shard_symbols(universe, 0, 1) == sorted(universe)


def test_assignment_is_stable_regardless_of_input_order_or_process() -> None:
    """Restart-safe / coordination-free: two independent processes (here,
    simulated by calling with the list in a different order) derive the
    identical assignment with no message exchanged."""
    universe = _universe()
    forward = shard_symbols(universe, 1, 4)
    shuffled = shard_symbols(list(reversed(universe)), 1, 4)
    assert forward == shuffled


def test_shard_index_out_of_range_yields_nothing() -> None:
    assert shard_symbols(_universe(), 5, 4) == []


@pytest.mark.parametrize("shard_total", [2, 3, 4])
def test_balance_report(shard_total: int, capsys: pytest.CaptureFixture[str]) -> None:
    """Not an assertion of perfect balance (crc32 over a heavy-tailed,
    volume-weighted universe can put two majors on the same shard by chance)
    -- prints the counts so the orchestrator has evidence to pick N."""
    universe = _universe()
    counts = [len(shard_symbols(universe, i, shard_total)) for i in range(shard_total)]
    assert sum(counts) == len(universe)
    print(f"N={shard_total} counts={counts} min={min(counts)} max={max(counts)}")
