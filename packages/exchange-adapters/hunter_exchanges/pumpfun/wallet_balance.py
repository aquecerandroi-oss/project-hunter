"""The balance-delta reading of a watched wallet's fill (``wallet_fills.py``
§2): a swap on PumpSwap, whose ``BuyEvent``/``SellEvent`` layout this repo has
not captured (``docs/PUMPFUN-ONCHAIN.md`` §2.4 lists the fields, not the
bytes). The wallet's SOL change (network fee added back, wSOL folded in) and
the one token account whose balance moved say ``buy``/``sell`` and how much —
no fee breakdown, and ``decode = 'balance_delta'`` says so.

Kept out of ``wallet_fills.py`` only to fit the repo's file-size budget.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, cast

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID

__all__ = [
    "CURVE_TOKEN_DECIMALS",
    "PUMPSWAP_PROGRAM_ID",
    "WSOL_MINT",
    "Side",
    "Venue",
    "from_balances",
]

PUMPSWAP_PROGRAM_ID = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
"""PumpSwap (Pump AMM), ``docs/PUMPFUN-ONCHAIN.md`` §0."""

WSOL_MINT = "So11111111111111111111111111111111111111112"
CURVE_TOKEN_DECIMALS = 6

Side = Literal["buy", "sell", "unknown"]
Venue = Literal["curve", "pool"]


def _obj(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _seq(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _token_deltas(meta: dict[str, Any], wallet: str) -> dict[str, tuple[int, int]]:
    """``mint -> (delta in base units, decimals)`` for the wallet's own token accounts."""
    pre: dict[str, tuple[int, int]] = {}
    post: dict[str, tuple[int, int]] = {}
    for label, into in (("preTokenBalances", pre), ("postTokenBalances", post)):
        for entry_any in _seq(meta.get(label)):
            entry = _obj(entry_any)
            if entry.get("owner") != wallet:
                continue
            amount = _obj(entry.get("uiTokenAmount"))
            try:
                units = int(str(amount.get("amount", "0")))
                decimals = int(amount.get("decimals", CURVE_TOKEN_DECIMALS))
            except (TypeError, ValueError):
                continue
            mint = str(entry.get("mint", ""))
            held, _ = into.get(mint, (0, decimals))
            into[mint] = (held + units, decimals)
    deltas: dict[str, tuple[int, int]] = {}
    for mint in set(pre) | set(post):
        before, decimals = pre.get(mint, (0, post.get(mint, (0, CURVE_TOKEN_DECIMALS))[1]))
        after, _ = post.get(mint, (0, decimals))
        if after != before:
            deltas[mint] = (after - before, decimals)
    return deltas


def _sol_change(meta: dict[str, Any], keys: list[str], wallet: str, fee: int) -> int | None:
    """The wallet's lamport change with the network fee it paid added back."""
    try:
        index = keys.index(wallet)
        pre = int(_seq(meta.get("preBalances"))[index])
        post = int(_seq(meta.get("postBalances"))[index])
    except (ValueError, IndexError, TypeError):
        return None
    return post - pre + fee


def from_balances(
    tx: dict[str, Any], keys: list[str], *, wallet: str, network_fee: int
) -> tuple[Side, Venue | None, str | None, int | None, Decimal | None, dict[str, Any]]:
    """The balance-delta reading; ``side = 'unknown'`` names why it did not apply."""
    meta = _obj(tx.get("meta"))
    programs = [p for p in (PUMP_PROGRAM_ID, PUMPSWAP_PROGRAM_ID) if p in keys]
    deltas = _token_deltas(meta, wallet)
    sol_change = _sol_change(meta, keys, wallet, network_fee)
    wsol = deltas.pop(WSOL_MINT, None)
    if sol_change is not None and wsol is not None:
        sol_change += wsol[0]
    raw: dict[str, Any] = {
        "decode": "balance_delta",
        "programs": programs,
        "sol_change_lamports": sol_change,
        "network_fee_lamports": network_fee,
        "token_deltas": {mint: units for mint, (units, _) in deltas.items()},
    }
    if PUMPSWAP_PROGRAM_ID not in programs:
        reason = "no_trade_event_for_wallet" if PUMP_PROGRAM_ID in programs else "no_known_venue"
        return "unknown", None, None, None, None, {**raw, "reason": reason}
    if sol_change is None:
        return "unknown", None, None, None, None, {**raw, "reason": "wallet_not_in_transaction"}
    if len(deltas) != 1:
        reason = "no_token_delta" if not deltas else "multiple_token_deltas"
        return "unknown", None, None, None, None, {**raw, "reason": reason}
    ((mint, (units, decimals)),) = deltas.items()
    if (units > 0) == (sol_change < 0) and sol_change != 0:
        side: Side = "buy" if units > 0 else "sell"
        tokens = Decimal(abs(units)) / Decimal(10**decimals)
        return side, "pool", mint, abs(sol_change), tokens, {**raw, "token_decimals": decimals}
    return "unknown", None, mint, None, None, {**raw, "reason": "sol_leg_sign_mismatch"}
