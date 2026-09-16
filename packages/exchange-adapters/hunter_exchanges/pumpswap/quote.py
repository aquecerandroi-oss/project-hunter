"""Local sell quote on a PumpSwap pool — integer lamports/subunits, pure (T4.29a).

**Reserves.** ``docs/PUMPFUN-ONCHAIN.md`` §2.2's "effective quote reserves"
rule: the quote side of the constant product is not the vault's raw balance,
it is ``pool_quote_token_account.amount + Pool.virtual_quote_reserves`` — this
package never assumes the second term is zero (``decode.py``'s finding that
two of three pools read live carry a non-zero one).

**Formula.** The pool is a constant-product AMM (``docs/PUMP_SWAP_README.md``,
same family as the bonding curve). No PumpSwap-specific rounding rule is
published the way the bonding curve's ``buy``/``sell`` was reverse-engineered
against real fills in T4.8 — this module uses the same shape as
``hunter_exchanges.pumpfun.quote.sell_proceeds`` (``floor(a·Q/(B+a))``, the
standard `x*y=k` sell-into-pool formula), **not yet confirmed against a real
PumpSwap fill** (no wallet exists to produce one — see
``.claude/state/notes-T4.29a.md`` "not proven"). Fees are taken from the
program's own ``GlobalConfig`` (``lp_fee_basis_points``,
``protocol_fee_basis_points``, ``coin_creator_fee_basis_points`` — **never
hardcoded**, read live at call time), each rounded up independently on the
gross quote amount, mirroring how the bonding curve's protocol and creator
fees are both ``ceil``'d separately.

**Worked example (real numbers, T4.29a, pool ``F5MkE4Yf73TkeSKLv3Mr3yrGJpFg3g7sspaCosVYyxaQ``,
slot 447586178):** ``pool_base_token_account.amount = 964_405_811_222_437``,
``pool_quote_token_account.amount = 751_101_815``,
``Pool.virtual_quote_reserves = 17_584_505_291`` →
``effective_quote_reserves = 18_335_607_106``. Selling ``a = 1_000_000_000``
base subunits (1 000 tokens at 6 decimals): gross quote
``= floor(1_000_000_000 * 18_335_607_106 / (964_405_811_222_437 +
1_000_000_000)) = 19_012`` lamports. Fees at the bps read live that same
slot (``lp=20``, ``protocol=5``, ``coin_creator=5``, 30 bps total):
``ceil(19_012*20/10_000)=39``, ``ceil(19_012*5/10_000)=10`` (twice, protocol
and creator) → net ``= 19_012 - 39 - 10 - 10 = 18_953`` lamports. All of this
is exercised, with these exact numbers, in
``tests/unit/test_pumpswap_quote.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from hunter_exchanges.pumpswap.decode import GlobalConfig, Pool

__all__ = [
    "MAX_SLIPPAGE_BPS",
    "PoolReserves",
    "SellQuote",
    "effective_quote_reserves",
    "pool_reserves",
    "quote_pool_sell",
    "sell_proceeds",
]

_BPS = 10_000
MAX_SLIPPAGE_BPS = 5_000
"""Same ceiling as the bonding curve's quote — asking for more is a typo."""


@dataclass(frozen=True, slots=True)
class PoolReserves:
    """Raw on-chain reserves of one pool, base/quote subunits."""

    base: int
    effective_quote: int

    def __post_init__(self) -> None:
        if self.base <= 0:
            raise ValueError("base reserves must be positive")
        if self.effective_quote <= 0:
            raise ValueError("effective quote reserves must be positive")


def effective_quote_reserves(pool: Pool, pool_quote_token_account_amount: int) -> int:
    """``pool_quote_token_account.amount + Pool.virtual_quote_reserves`` —
    never the raw vault balance alone (§ module docstring)."""
    total = pool_quote_token_account_amount + pool.virtual_quote_reserves
    if total < 0:
        raise ValueError("effective quote reserves must not be negative")
    return total


def pool_reserves(
    pool: Pool, *, pool_base_token_account_amount: int, pool_quote_token_account_amount: int
) -> PoolReserves:
    return PoolReserves(
        base=pool_base_token_account_amount,
        effective_quote=effective_quote_reserves(pool, pool_quote_token_account_amount),
    )


def sell_proceeds(reserves: PoolReserves, base_amount_in: int) -> int:
    """Gross quote (pre-fee) the pool pays for ``base_amount_in``:
    ``floor(a * effective_quote / (base + a))`` — same shape as the bonding
    curve's sell, not yet confirmed against a real PumpSwap fill."""
    if base_amount_in <= 0:
        raise ValueError("base_amount_in must be positive")
    return base_amount_in * reserves.effective_quote // (reserves.base + base_amount_in)


def _ceil_bps(amount: int, bps: int) -> int:
    return -(-amount * bps // _BPS)


def _check_slippage(max_slippage_bps: int) -> None:
    if isinstance(max_slippage_bps, bool) or not 0 <= max_slippage_bps <= MAX_SLIPPAGE_BPS:
        raise ValueError(f"max_slippage_bps must be an int in 0..{MAX_SLIPPAGE_BPS}")


@dataclass(frozen=True, slots=True)
class SellQuote:
    base_amount_in: int
    gross_quote_amount: int
    lp_fee: int
    protocol_fee: int
    coin_creator_fee: int
    net_quote_amount: int
    min_quote_amount_out: int
    max_slippage_bps: int
    price_impact_bps: int


def _impact_bps(gross: int, base_amount_in: int, reserves: PoolReserves) -> int:
    marginal_num, marginal_den = reserves.effective_quote, reserves.base
    return abs(gross * marginal_den * _BPS // (base_amount_in * marginal_num) - _BPS)


def quote_pool_sell(
    reserves: PoolReserves,
    base_amount_in: int,
    config: GlobalConfig,
    *,
    max_slippage_bps: int,
) -> SellQuote:
    """Price a sell of ``base_amount_in`` base subunits on the pool, fees read
    live from ``GlobalConfig`` — never a hardcoded percentage."""
    _check_slippage(max_slippage_bps)
    gross = sell_proceeds(reserves, base_amount_in)
    lp_fee = _ceil_bps(gross, config.lp_fee_basis_points)
    protocol_fee = _ceil_bps(gross, config.protocol_fee_basis_points)
    coin_creator_fee = _ceil_bps(gross, config.coin_creator_fee_basis_points)
    net = gross - lp_fee - protocol_fee - coin_creator_fee
    if net <= 0:
        raise ValueError("sell proceeds do not cover the fees")
    return SellQuote(
        base_amount_in=base_amount_in,
        gross_quote_amount=gross,
        lp_fee=lp_fee,
        protocol_fee=protocol_fee,
        coin_creator_fee=coin_creator_fee,
        net_quote_amount=net,
        min_quote_amount_out=net * (_BPS - max_slippage_bps) // _BPS,
        max_slippage_bps=max_slippage_bps,
        price_impact_bps=_impact_bps(gross, base_amount_in, reserves),
    )
