"""Local quote on the bonding curve — integer lamports, the program's own rounding.

Everything here is pure: reserves in, numbers out. The formulas are the ones
``docs/PUMPFUN-ONCHAIN.md`` §1.4b describes, **re-derived in T4.8 against two
real mainnet fills** (``tests/fixtures/pumpfun/rpc_tx_probe_raw.json`` — a sell —
and ``rpc_tx_buy_raw.json`` — a buy), lamport-exact:

- buy: ``sol_amount = floor(a * vsol / (vtok - a)) + 1``
- sell: ``sol_amount = floor(a * vsol / (vtok + a))``
- fees: ``ceil(sol_amount * bps / 10_000)`` **per component** — the protocol
  fee and the creator/cashback fee are rounded up separately, and both leave
  the trader's wallet (balance deltas reconciled in ``test_pumpfun_quote.py``).

The fee basis points are an **input** (:class:`FeeBps`), never a constant:
the program computes them per trade through ``GetFeesWithQuoteMint`` and
reports them in ``TradeEvent``. What the official fee page says the bonding
curve tier is *today* is exposed as :data:`BONDING_CURVE_FEE_TIER_2026_05_20`
for callers that have no fresher number, with the date in its name so nobody
mistakes it for protocol truth (T4.0d §1.4b, ``curve.py`` finding).

Slippage is explicit: every quote needs ``max_slippage_bps`` and refuses a
missing or absurd value — the instruction has no "%" field, only
``max_sol_cost`` / ``min_sol_output`` in lamports (§9.1 item 4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "BONDING_CURVE_FEE_TIER_2026_05_20",
    "MAX_SLIPPAGE_BPS",
    "BuyQuote",
    "CurveReserves",
    "FeeBps",
    "GlobalParams",
    "SellQuote",
    "buy_cost",
    "curve_progress_bps",
    "parse_global_params",
    "quote_buy",
    "quote_buy_for_budget",
    "quote_sell",
    "sell_proceeds",
]

_BPS = 10_000
MAX_SLIPPAGE_BPS = 5_000
"""A quote asking for more than 50 % slippage is a typo, not a policy."""


@dataclass(frozen=True, slots=True)
class FeeBps:
    """Basis points the program charges on ``sol_amount``: protocol + creator (or
    cashback, which takes the creator share on cashback coins)."""

    protocol: int
    creator: int

    def __post_init__(self) -> None:
        if self.protocol < 0 or self.creator < 0 or self.protocol + self.creator >= _BPS:
            raise ValueError("fee basis points must be >= 0 and sum below 10_000")

    @property
    def total(self) -> int:
        return self.protocol + self.creator


BONDING_CURVE_FEE_TIER_2026_05_20 = FeeBps(protocol=95, creator=30)
"""``pump.fun/docs/fees`` "Last Updated: 20 May 2026", row "Bonding curve":
0.950 % + 0.300 % = 1.25 %. Matched by ``GetFeesWithQuoteMint`` return data in
both T4.8 fixtures (``AAAAAAAAAABfAAAAAAAAAB4AAAAAAAAA`` = lp 0, protocol 95,
creator 30). A tier, not a law: read ``TradeEvent`` for the fill."""


@dataclass(frozen=True, slots=True)
class CurveReserves:
    """Raw on-chain reserves (lamports / token subunits) of one bonding curve."""

    virtual_sol: int
    virtual_token: int
    real_sol: int
    real_token: int
    complete: bool = False

    def __post_init__(self) -> None:
        if min(self.virtual_sol, self.virtual_token, self.real_sol, self.real_token) < 0:
            raise ValueError("reserves are non-negative integers")
        if self.virtual_token == 0:
            raise ValueError("virtual_token reserves must be positive")

    @property
    def marginal_price_lamports_per_token(self) -> float:
        """Reference only — quotes never use a float."""
        return self.virtual_sol / self.virtual_token


@dataclass(frozen=True, slots=True)
class GlobalParams:
    """``GET /global-params/{created_timestamp_ms}`` (``docs/PUMPFUN.md`` §1.1 #19):
    the curve parameters in force when the coin was created."""

    slot: int
    signature: str
    initial_virtual_token_reserves: int
    initial_virtual_sol_reserves: int
    initial_real_token_reserves: int
    token_total_supply: int
    fee_basis_points: int
    timestamp: int
    initial_virtual_quote_reserves: int | None = None


def parse_global_params(raw: dict[str, Any]) -> GlobalParams:
    def integer(key: str) -> int:
        value = raw[key]
        if isinstance(value, bool) or not isinstance(value, int | str):
            raise ValueError(f"global-params field {key!r} must be an integer")
        return int(value)

    quote = raw.get("initial_virtual_quote_reserves")
    return GlobalParams(
        slot=integer("slot"),
        signature=str(raw["signature"]),
        initial_virtual_token_reserves=integer("initial_virtual_token_reserves"),
        initial_virtual_sol_reserves=integer("initial_virtual_sol_reserves"),
        initial_real_token_reserves=integer("initial_real_token_reserves"),
        token_total_supply=integer("token_total_supply"),
        fee_basis_points=integer("fee_basis_points"),
        timestamp=integer("timestamp"),
        initial_virtual_quote_reserves=None if quote is None else int(quote),
    )


def curve_progress_bps(reserves: CurveReserves, params: GlobalParams) -> int:
    """``1 − real_token / initial_real_token`` in basis points (§3.1 window check)."""
    if params.initial_real_token_reserves <= 0:
        raise ValueError("progress denominator missing")
    sold = params.initial_real_token_reserves - reserves.real_token
    return max(0, min(_BPS, sold * _BPS // params.initial_real_token_reserves))


def _ceil_bps(amount: int, bps: int) -> int:
    return -(-amount * bps // _BPS)


@dataclass(frozen=True, slots=True)
class BuyQuote:
    token_amount: int
    sol_amount: int
    protocol_fee: int
    creator_fee: int
    total_cost: int
    max_sol_cost: int
    max_slippage_bps: int
    price_impact_bps: int
    reserves_after: CurveReserves


@dataclass(frozen=True, slots=True)
class SellQuote:
    token_amount: int
    sol_amount: int
    protocol_fee: int
    creator_fee: int
    net_proceeds: int
    min_sol_output: int
    max_slippage_bps: int
    price_impact_bps: int
    reserves_after: CurveReserves


def _check_slippage(max_slippage_bps: int) -> None:
    if isinstance(max_slippage_bps, bool) or not 0 <= max_slippage_bps <= MAX_SLIPPAGE_BPS:
        raise ValueError(f"max_slippage_bps must be an int in 0..{MAX_SLIPPAGE_BPS}")


def buy_cost(reserves: CurveReserves, token_amount: int) -> int:
    """SOL the curve takes for ``token_amount`` (pre-fee): ``floor(a·vsol/(vtok−a)) + 1``."""
    if token_amount <= 0:
        raise ValueError("token_amount must be positive")
    if reserves.complete:
        raise ValueError("curve_complete")
    if token_amount > reserves.real_token:
        raise ValueError("token_amount exceeds the curve's real token reserves")
    return token_amount * reserves.virtual_sol // (reserves.virtual_token - token_amount) + 1


def sell_proceeds(reserves: CurveReserves, token_amount: int) -> int:
    """SOL the curve pays for ``token_amount`` (pre-fee): ``floor(a·vsol/(vtok+a))``."""
    if token_amount <= 0:
        raise ValueError("token_amount must be positive")
    if reserves.complete:
        raise ValueError("curve_complete")
    return token_amount * reserves.virtual_sol // (reserves.virtual_token + token_amount)


def _impact_bps(sol_amount: int, token_amount: int, reserves: CurveReserves) -> int:
    """Average fill price vs. the marginal price before the trade, in bps (integer math)."""
    avg_num, avg_den = sol_amount, token_amount
    mrg_num, mrg_den = reserves.virtual_sol, reserves.virtual_token
    return abs(avg_num * mrg_den * _BPS // (avg_den * mrg_num) - _BPS)


def quote_buy(
    reserves: CurveReserves, token_amount: int, fees: FeeBps, *, max_slippage_bps: int
) -> BuyQuote:
    _check_slippage(max_slippage_bps)
    sol_amount = buy_cost(reserves, token_amount)
    protocol_fee = _ceil_bps(sol_amount, fees.protocol)
    creator_fee = _ceil_bps(sol_amount, fees.creator)
    total = sol_amount + protocol_fee + creator_fee
    after = CurveReserves(
        virtual_sol=reserves.virtual_sol + sol_amount,
        virtual_token=reserves.virtual_token - token_amount,
        real_sol=reserves.real_sol + sol_amount,
        real_token=reserves.real_token - token_amount,
        complete=reserves.real_token - token_amount == 0,
    )
    return BuyQuote(
        token_amount=token_amount,
        sol_amount=sol_amount,
        protocol_fee=protocol_fee,
        creator_fee=creator_fee,
        total_cost=total,
        max_sol_cost=-(-total * (_BPS + max_slippage_bps) // _BPS),
        max_slippage_bps=max_slippage_bps,
        price_impact_bps=_impact_bps(sol_amount, token_amount, reserves),
        reserves_after=after,
    )


def quote_buy_for_budget(
    reserves: CurveReserves, budget_lamports: int, fees: FeeBps, *, max_slippage_bps: int
) -> BuyQuote:
    """The largest whole-subunit buy whose **total** cost (fees included) fits
    ``budget_lamports`` — the budget is a ceiling, never a target (§3 "teto é teto")."""
    if budget_lamports <= 0:
        raise ValueError("budget must be positive")
    if reserves.complete:
        raise ValueError("curve_complete")
    # Largest pre-fee spend whose per-component ceil'd fees still fit the budget.
    spend = budget_lamports * _BPS // (_BPS + fees.total)
    while (
        spend > 0
        and spend + _ceil_bps(spend, fees.protocol) + _ceil_bps(spend, fees.creator)
        > budget_lamports
    ):
        spend -= 1
    tokens = spend * reserves.virtual_token // (reserves.virtual_sol + spend)
    tokens = min(tokens, reserves.real_token)
    # ``buy_cost`` adds the program's ``+1`` lamport; step down until the whole
    # cost (curve + fees) fits. Converges in a handful of single-subunit steps.
    while tokens > 0:
        quote = quote_buy(reserves, tokens, fees, max_slippage_bps=max_slippage_bps)
        if quote.total_cost <= budget_lamports:
            return quote
        tokens -= max(1, (quote.total_cost - budget_lamports) * tokens // quote.total_cost)
    raise ValueError("budget too small for one token subunit plus fees")


def quote_sell(
    reserves: CurveReserves, token_amount: int, fees: FeeBps, *, max_slippage_bps: int
) -> SellQuote:
    _check_slippage(max_slippage_bps)
    sol_amount = sell_proceeds(reserves, token_amount)
    protocol_fee = _ceil_bps(sol_amount, fees.protocol)
    creator_fee = _ceil_bps(sol_amount, fees.creator)
    net = sol_amount - protocol_fee - creator_fee
    if net <= 0:
        raise ValueError("sell proceeds do not cover the fees")
    after = CurveReserves(
        virtual_sol=reserves.virtual_sol - sol_amount,
        virtual_token=reserves.virtual_token + token_amount,
        real_sol=max(0, reserves.real_sol - sol_amount),
        real_token=reserves.real_token + token_amount,
        complete=False,
    )
    return SellQuote(
        token_amount=token_amount,
        sol_amount=sol_amount,
        protocol_fee=protocol_fee,
        creator_fee=creator_fee,
        net_proceeds=net,
        min_sol_output=net * (_BPS - max_slippage_bps) // _BPS,
        max_slippage_bps=max_slippage_bps,
        price_impact_bps=_impact_bps(sol_amount, token_amount, reserves),
        reserves_after=after,
    )
