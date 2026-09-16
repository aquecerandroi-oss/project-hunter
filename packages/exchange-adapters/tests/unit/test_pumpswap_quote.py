"""``quote_pool_sell`` against the real numbers in ``quote.py``'s docstring
(pool ``F5MkE4Yf73TkeSKLv3Mr3yrGJpFg3g7sspaCosVYyxaQ``, slot 447586178,
T4.29a) — every intermediate number worked by hand in the module docstring
and checked here, plus the malformed-input edges.
"""

from __future__ import annotations

import pytest

from hunter_exchanges.pumpswap.decode import GlobalConfig, Pool
from hunter_exchanges.pumpswap.quote import (
    MAX_SLIPPAGE_BPS,
    PoolReserves,
    effective_quote_reserves,
    quote_pool_sell,
    sell_proceeds,
)

BASE_RESERVES = 964_405_811_222_437
QUOTE_RAW = 751_101_815
VIRTUAL_QUOTE = 17_584_505_291
EFFECTIVE_QUOTE = QUOTE_RAW + VIRTUAL_QUOTE


def _global_config(**overrides: int) -> GlobalConfig:
    defaults = dict(
        lp_fee_basis_points=20, protocol_fee_basis_points=5, coin_creator_fee_basis_points=5
    )
    defaults.update(overrides)
    return GlobalConfig(
        admin="admin",
        disable_flags=0,
        protocol_fee_recipients=tuple(f"recipient{i}" for i in range(8)),
        **defaults,
    )


def _pool_with_virtual_quote_reserves(virtual_quote_reserves: int) -> Pool:
    placeholder = "1" * 32
    return Pool(
        pool_bump=255,
        index=0,
        creator=placeholder,
        base_mint=placeholder,
        quote_mint=placeholder,
        lp_mint=placeholder,
        pool_base_token_account=placeholder,
        pool_quote_token_account=placeholder,
        lp_supply=0,
        coin_creator=placeholder,
        is_mayhem_mode=False,
        is_cashback_coin=False,
        virtual_quote_reserves=virtual_quote_reserves,
    )


def test_effective_quote_reserves_adds_virtual_component() -> None:
    pool = _pool_with_virtual_quote_reserves(VIRTUAL_QUOTE)
    assert effective_quote_reserves(pool, QUOTE_RAW) == EFFECTIVE_QUOTE


def test_sell_proceeds_matches_worked_example() -> None:
    reserves = PoolReserves(base=BASE_RESERVES, effective_quote=EFFECTIVE_QUOTE)
    assert sell_proceeds(reserves, 1_000_000_000) == 19_012


def test_quote_pool_sell_matches_worked_example() -> None:
    reserves = PoolReserves(base=BASE_RESERVES, effective_quote=EFFECTIVE_QUOTE)
    config = _global_config()
    quote = quote_pool_sell(reserves, 1_000_000_000, config, max_slippage_bps=100)
    assert quote.gross_quote_amount == 19_012
    assert quote.lp_fee == 39
    assert quote.protocol_fee == 10
    assert quote.coin_creator_fee == 10
    assert quote.net_quote_amount == 18_953
    assert quote.min_quote_amount_out == 18_953 * 9_900 // 10_000


def test_fees_are_never_hardcoded_reading_config_changes_the_quote() -> None:
    reserves = PoolReserves(base=BASE_RESERVES, effective_quote=EFFECTIVE_QUOTE)
    low_fee = quote_pool_sell(
        reserves, 1_000_000_000, _global_config(lp_fee_basis_points=0), max_slippage_bps=0
    )
    high_fee = quote_pool_sell(
        reserves, 1_000_000_000, _global_config(lp_fee_basis_points=200), max_slippage_bps=0
    )
    assert low_fee.net_quote_amount > high_fee.net_quote_amount


def test_zero_or_negative_base_amount_rejected() -> None:
    reserves = PoolReserves(base=BASE_RESERVES, effective_quote=EFFECTIVE_QUOTE)
    with pytest.raises(ValueError, match="positive"):
        sell_proceeds(reserves, 0)


def test_slippage_out_of_range_rejected() -> None:
    reserves = PoolReserves(base=BASE_RESERVES, effective_quote=EFFECTIVE_QUOTE)
    with pytest.raises(ValueError, match="max_slippage_bps"):
        quote_pool_sell(
            reserves, 1_000_000_000, _global_config(), max_slippage_bps=MAX_SLIPPAGE_BPS + 1
        )


def test_pool_reserves_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match="base reserves"):
        PoolReserves(base=0, effective_quote=1)
    with pytest.raises(ValueError, match="effective quote"):
        PoolReserves(base=1, effective_quote=0)


def test_sell_proceeds_never_exceeds_effective_quote_reserves() -> None:
    """A sell of the entire base supply cannot drain more than the pool holds
    (constant product asymptote), sanity-checking the formula's shape."""
    reserves = PoolReserves(base=BASE_RESERVES, effective_quote=EFFECTIVE_QUOTE)
    huge_sell = sell_proceeds(reserves, BASE_RESERVES * 1000)
    assert huge_sell < EFFECTIVE_QUOTE
