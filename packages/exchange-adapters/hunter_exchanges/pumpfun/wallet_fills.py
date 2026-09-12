"""A watched wallet's fills, read from one ``getTransaction`` result (T4.12).

Three readings, in order of trust, and the third is a confession:

1. **The pump program's ``TradeEvent``** (``trade_event.py``) — exact: the SOL
   leg, the protocol fee, the creator fee and the cashback come from the event
   itself, and T4.8 reconciled them lamport-exact against the trader's balance.
   Only an event whose ``user`` is the watched wallet counts; the wallet that
   merely paid the network fee of someone else's fill is not a trader.
2. **The wallet's own balance deltas** — for a swap on PumpSwap (``pAMM…`` among
   the accounts), whose ``BuyEvent``/``SellEvent`` layout this repo has not
   captured (``docs/PUMPFUN-ONCHAIN.md`` §2.4 lists the fields, not the bytes).
   The wallet's SOL change (network fee added back, wSOL folded in) and the one
   token account whose balance moved say ``buy``/``sell`` and how much. It is
   what the chain says the wallet gave and got — no fee breakdown, and
   ``decode = 'balance_delta'`` says so.
3. **``unknown``** — everything else (a transfer, an ATA creation, a trade the
   wallet did not make, a quote that is not SOL): the reason by name and a
   bounded ``raw`` so the row can be read later, and no number invented.

A failed transaction (``meta.err``) yields nothing: a reverted fill is not a
fill. Amounts are integers in lamports and ``Decimal`` tokens; nothing here
touches a socket or a clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, cast

from hunter_exchanges.pumpfun.decode import NATIVE_SOL_QUOTE_MINT, PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.trade_event import TradeEvent, trade_events_from_transaction

__all__ = [
    "CURVE_TOKEN_DECIMALS",
    "PUMPSWAP_PROGRAM_ID",
    "WSOL_MINT",
    "Decode",
    "Side",
    "Venue",
    "WalletFill",
    "wallet_fills_from_transaction",
]

PUMPSWAP_PROGRAM_ID = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
"""PumpSwap (Pump AMM), ``docs/PUMPFUN-ONCHAIN.md`` §0."""

WSOL_MINT = "So11111111111111111111111111111111111111112"
CURVE_TOKEN_DECIMALS = 6
_RAW_KEYS = 40
_RAW_LOG_LINES = 12

Side = Literal["buy", "sell", "unknown"]
Venue = Literal["curve", "pool"]
Decode = Literal["trade_event", "balance_delta", "none"]


@dataclass(frozen=True, slots=True)
class WalletFill:
    """One row of ``meme_wallet_trades`` before it is a row."""

    wallet: str
    signature: str
    event_index: int
    slot: int
    block_time: datetime | None
    mint: str | None
    side: Side
    venue: Venue | None
    sol_lamports: int | None
    """The trade leg: ``sol_amount`` of the event, or the SOL delta net of the
    network fee on the balance path."""
    fee_lamports: int | None
    """Every deduction on top of the leg (protocol + creator + cashback, and the
    network fee when the wallet paid it)."""
    token_amount: Decimal | None
    decode: Decode
    raw: dict[str, Any]

    @property
    def is_fill(self) -> bool:
        return self.side != "unknown"

    @property
    def sol_spent_lamports(self) -> int | None:
        """A buy: what left the wallet, lamport-exact."""
        if self.side != "buy" or self.sol_lamports is None or self.fee_lamports is None:
            return None
        return self.sol_lamports + self.fee_lamports

    @property
    def sol_received_lamports(self) -> int | None:
        """A sell: what reached the wallet, lamport-exact."""
        if self.side != "sell" or self.sol_lamports is None or self.fee_lamports is None:
            return None
        return self.sol_lamports - self.fee_lamports


def _obj(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _seq(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _account_keys(tx: dict[str, Any]) -> list[str]:
    """Static keys then the loaded (lookup-table) ones — the order balances index."""
    meta = _obj(tx.get("meta"))
    message = _obj(_obj(tx.get("transaction")).get("message"))
    loaded = _obj(meta.get("loadedAddresses"))
    keys = _seq(message.get("accountKeys")) + _seq(loaded.get("writable"))
    keys += _seq(loaded.get("readonly"))
    return [str(key) for key in keys]


def _block_time(tx: dict[str, Any]) -> datetime | None:
    raw = tx.get("blockTime")
    if isinstance(raw, int) and raw > 0:
        return datetime.fromtimestamp(raw, tz=UTC)
    return None


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


def _from_event(
    event: TradeEvent,
    *,
    wallet: str,
    signature: str,
    event_index: int,
    slot: int,
    block_time: datetime | None,
    network_fee: int,
) -> WalletFill:
    raw: dict[str, Any] = {
        "decode": "trade_event",
        "ix_name": event.ix_name,
        "fees": {
            "protocol": event.fee,
            "creator": event.creator_fee,
            "cashback": event.cashback,
            "network": network_fee,
        },
        "fee_bps": {
            "protocol": event.fee_basis_points,
            "creator": event.creator_fee_basis_points,
            "cashback": event.cashback_fee_basis_points,
        },
        "reserves_after": {
            "virtual_sol_reserves": event.virtual_sol_reserves,
            "virtual_token_reserves": event.virtual_token_reserves,
            "real_sol_reserves": event.real_sol_reserves,
            "real_token_reserves": event.real_token_reserves,
        },
        "quote_mint": event.quote_mint,
        "mayhem_mode": event.mayhem_mode,
        "timestamp": event.timestamp,
    }
    at = block_time or (
        datetime.fromtimestamp(event.timestamp, tz=UTC) if event.timestamp > 0 else None
    )
    sol_quoted = event.quote_mint == NATIVE_SOL_QUOTE_MINT or (
        event.quote_amount == event.sol_amount and event.sol_amount > 0
    )
    if not sol_quoted:
        raw["reason"] = "unsupported_quote"
        return WalletFill(
            wallet, signature, event_index, slot, at, event.mint, "unknown", None, None, None,
            None, "none", raw,
        )  # fmt: skip
    return WalletFill(
        wallet=wallet,
        signature=signature,
        event_index=event_index,
        slot=slot,
        block_time=at,
        mint=event.mint,
        side="buy" if event.is_buy else "sell",
        venue="curve",
        sol_lamports=event.sol_amount,
        fee_lamports=event.fee + event.creator_fee + event.cashback + network_fee,
        token_amount=Decimal(event.token_amount) / Decimal(10**CURVE_TOKEN_DECIMALS),
        decode="trade_event",
        raw=raw,
    )


def _from_balances(
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


def wallet_fills_from_transaction(
    tx: dict[str, Any],
    *,
    wallet: str,
    signature: str,
    slot_hint: int = 0,
    block_time_hint: datetime | None = None,
) -> tuple[WalletFill, ...]:
    """Every fill of ``wallet`` in one ``getTransaction`` result (``encoding: json``).

    ``()`` for a failed transaction; otherwise at least one fill, the last
    resort being a single ``unknown`` that keeps the reason and the raw.
    """
    meta = _obj(tx.get("meta"))
    if meta.get("err") is not None:
        return ()
    malformed = not _obj(tx.get("transaction")) or not meta
    raw_slot = tx.get("slot")
    slot = raw_slot if isinstance(raw_slot, int) and raw_slot >= 0 else slot_hint
    block_time = _block_time(tx) or block_time_hint
    keys = _account_keys(tx)
    network_fee = int(meta.get("fee") or 0) if keys and keys[0] == wallet else 0
    event_error: str | None = None
    try:
        events = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    except ValueError as exc:
        events, event_error = (), str(exc)[:120]
    fills: list[WalletFill] = []
    for event in events:
        if event.user != wallet:
            continue
        fills.append(
            _from_event(
                event,
                wallet=wallet,
                signature=signature,
                event_index=len(fills),
                slot=slot,
                block_time=block_time,
                network_fee=network_fee if not fills else 0,
            )
        )
    if fills:
        return tuple(fills)
    side, venue, mint, sol, tokens, raw = _from_balances(
        tx, keys, wallet=wallet, network_fee=network_fee
    )
    if side == "unknown":
        raw = {
            **raw,
            "reason": "malformed_transaction" if malformed else raw.get("reason"),
            "err": meta.get("err"),
            "event_error": event_error,
            "account_keys": keys[:_RAW_KEYS],
            "log_head": [str(line) for line in _seq(meta.get("logMessages"))[:_RAW_LOG_LINES]],
        }
        return (
            WalletFill(
                wallet,
                signature,
                0,
                slot,
                block_time,
                mint,
                "unknown",
                None,
                None,
                None,
                None,
                "none",
                raw,
            ),  # fmt: skip
        )
    return (
        WalletFill(
            wallet=wallet,
            signature=signature,
            event_index=0,
            slot=slot,
            block_time=block_time,
            mint=mint,
            side=side,
            venue=venue,
            sol_lamports=sol,
            fee_lamports=network_fee,
            token_amount=tokens,
            decode="balance_delta",
            raw=raw,
        ),
    )
