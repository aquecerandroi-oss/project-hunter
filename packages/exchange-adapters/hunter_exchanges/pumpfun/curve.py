"""Bonding curve math (``docs/plans/T4-MEME-RADAR.md`` §3).

Constant-product curve: ``virtual_sol_reserves * virtual_token_reserves = k``.
Every function here takes whatever reserves it is handed — none of them
hardcode a token's *current* state, only the formula.

The two constants below are the reserves a **freshly created** pump.fun
token starts at, confirmed live twice: once in T4.0 research
(``.claude/state/notes-T4.0.md`` §2, mint
``AFbdSsy2ZW3eoTsWfkKMgpzC7VUA3EbY36RfM1i6ymPM``, 2026-09-12 01:37 BRT) and
again in this task's own capture
(``tests/fixtures/pumpfun/pumpportal_ws_capture_raw.jsonl``, message index 4,
``vSolInBondingCurve=30``, ``vTokensInBondingCurve=1073000000``). They are
exposed for tests and documentation, never consulted by :func:`marginal_price_sol`
or :func:`market_cap_sol`, whose whole point is to work on the *current*
reserves of any curve, initial or not.
"""

from __future__ import annotations

from decimal import Decimal

#: SOL a brand-new pump.fun bonding curve starts with (virtual reserve side).
INITIAL_VIRTUAL_SOL_RESERVES = Decimal(30)

#: Tokens (human units, 6 decimals already applied) a brand-new curve starts
#: with on the other side of the product.
INITIAL_VIRTUAL_TOKEN_RESERVES = Decimal(1_073_000_000)

#: pump.fun's own on-chain decimals for the two units this package converts
#: raw REST/RPC integers by (T4.0 §3: lamports for SOL, ``base_decimals=6``
#: for the token — confirmed against the live REST capture).
LAMPORTS_PER_SOL = Decimal(1_000_000_000)
TOKEN_SUBUNITS_PER_TOKEN = Decimal(1_000_000)

#: Trading fee on the bonding curve, split between creator and protocol
#: (T4.0 §3, confirmed on ``pump.fun/docs/bonding-curve`` and again by Astra
#: against ``pump.fun/docs/fees`` updated 2026-05-20 — never applied by this
#: module's formulas, which are pre-fee quote/execution prices; documented
#: here so a caller building a fill estimate does not forget it).
CURVE_TRADE_FEE_PCT = Decimal("1.25")


def marginal_price_sol(virtual_sol_reserves: Decimal, virtual_token_reserves: Decimal) -> Decimal:
    """SOL per token at the current point on the curve — the next infinitesimal unit's price.

    Not a fill price: buying a finite amount moves the curve (T4-MEME-RADAR.md
    §0/§4 — there is no orderbook depth here, only this formula's slippage).
    """
    if virtual_token_reserves <= 0:
        raise ValueError("virtual_token_reserves must be positive")
    return virtual_sol_reserves / virtual_token_reserves


def market_cap_sol(
    virtual_sol_reserves: Decimal,
    virtual_token_reserves: Decimal,
    total_supply: Decimal,
) -> Decimal:
    """Theoretical market cap in SOL: marginal price × total supply.

    Always theoretical (T4-MEME-RADAR.md §4) — nobody could sell
    ``total_supply`` at this price without moving the curve far below it.
    """
    return marginal_price_sol(virtual_sol_reserves, virtual_token_reserves) * total_supply


def is_graduated(real_token_reserves: Decimal, complete: bool) -> bool:
    """Whether the curve is complete; actual PumpSwap migration is a separate event.

    Astra's correction (``astra-review-t40-pumpfun.md``, must-fix
    "Graduação"): the documented criterion is ``real_token_reserves == 0``
    **and** ``complete == true`` — not a fixed SOL-accumulated or
    market-cap threshold. The ~85 SOL figure floating in secondary sources
    is a number *implied* by the initial constants above for one specific
    historical parameterization, not a threshold this function (or any
    other code in this package) hardcodes or checks against.
    """
    return complete and real_token_reserves == 0


def raw_lamports_to_sol(lamports: int) -> Decimal:
    """Convert an integer lamport count (REST/RPC wire format) to SOL."""
    return Decimal(lamports) / LAMPORTS_PER_SOL


def raw_subunits_to_tokens(subunits: int) -> Decimal:
    """Convert an integer token-subunit count (REST/RPC wire format) to whole tokens."""
    return Decimal(subunits) / TOKEN_SUBUNITS_PER_TOKEN


__all__ = [
    "CURVE_TRADE_FEE_PCT",
    "INITIAL_VIRTUAL_SOL_RESERVES",
    "INITIAL_VIRTUAL_TOKEN_RESERVES",
    "LAMPORTS_PER_SOL",
    "TOKEN_SUBUNITS_PER_TOKEN",
    "is_graduated",
    "marginal_price_sol",
    "market_cap_sol",
    "raw_lamports_to_sol",
    "raw_subunits_to_tokens",
]
