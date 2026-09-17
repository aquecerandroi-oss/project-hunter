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

from hunter_exchanges.pumpfun import rent as _rent
from hunter_exchanges.pumpfun.decode import NATIVE_SOL_QUOTE_MINT, PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.trade_event import TradeEvent, trade_events_from_transaction
from hunter_exchanges.pumpfun.wallet_balance import (
    CURVE_TOKEN_DECIMALS,
    PUMPSWAP_PROGRAM_ID,
    WSOL_MINT,
    Side,
    Venue,
)
from hunter_exchanges.pumpfun.wallet_balance import from_balances as _from_balances

__all__ = [
    "CURVE_TOKEN_DECIMALS",
    "PUMPSWAP_PROGRAM_ID",
    "WSOL_MINT",
    "Decode",
    "Side",
    "Venue",
    "WalletFill",
    "ata_close_refund_lamports",
    "rent_funded_by",
    "rent_labels",
    "wallet_fills_from_transaction",
]

_RAW_KEYS = 40
_RAW_LOG_LINES = 12

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
        """A sell: what reached the wallet, lamport-exact — plus the ATA rent an
        SPL Token ``CloseAccount`` refunded (T4.46: cash in, same as the leg)."""
        if self.side != "sell" or self.sol_lamports is None or self.fee_lamports is None:
            return None
        refund = self.raw.get("ata_rent_refund_lamports") or 0
        return self.sol_lamports - self.fee_lamports + int(refund)


def _obj(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _seq(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _key(entry: Any) -> str:
    """A ``jsonParsed`` account key is ``{"pubkey": ..., "signer": ..., ...}``;
    ``json``/``base58`` hands the string itself. R43 §5: without this, every
    key stringifies to a dict repr, no known program or wallet is ever found,
    and every fill of a ``jsonParsed`` transaction silently becomes ``unknown``."""
    if isinstance(entry, dict):
        return str(cast(dict[str, Any], entry).get("pubkey", ""))
    return str(entry)


def _account_keys(tx: dict[str, Any]) -> list[str]:
    """Static keys then the loaded (lookup-table) ones — the order balances index."""
    meta = _obj(tx.get("meta"))
    message = _obj(_obj(tx.get("transaction")).get("message"))
    loaded = _obj(meta.get("loadedAddresses"))
    keys = _seq(message.get("accountKeys")) + _seq(loaded.get("writable"))
    keys += _seq(loaded.get("readonly"))
    return [_key(key) for key in keys]


def _block_time(tx: dict[str, Any]) -> datetime | None:
    raw = tx.get("blockTime")
    if isinstance(raw, int) and raw > 0:
        return datetime.fromtimestamp(raw, tz=UTC)
    return None


def rent_funded_by(tx: dict[str, Any], wallet: str) -> dict[str, int]:
    """``new account -> lamports`` the wallet funded (T4.46/R43) — the
    accounting itself lives in :mod:`hunter_exchanges.pumpfun.rent`, to keep
    this module inside the repo's file-size budget."""
    return _rent.rent_funded_by(tx, _account_keys(tx), wallet)


def rent_labels(tx: dict[str, Any], wallet: str) -> tuple[int | None, int | None]:
    """``(ata_rent_lamports, account_rent_lamports)`` — see :mod:`.rent`."""
    return _rent.rent_labels(tx, _account_keys(tx), wallet)


def ata_close_refund_lamports(tx: dict[str, Any], wallet: str) -> int | None:
    """The ATA-rent refund of a full sell's ``CloseAccount`` — see :mod:`.rent`.
    Public so the executor's ``FillRecord`` (``build.py``) reads the same rule
    without duplicating it."""
    return _rent.ata_close_refund(tx, _account_keys(tx), wallet)


def _from_event(
    event: TradeEvent,
    *,
    wallet: str,
    signature: str,
    event_index: int,
    slot: int,
    block_time: datetime | None,
    network_fee: int,
    tx: dict[str, Any],
    keys: list[str],
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
    if event.is_buy:
        raw["ata_rent_lamports"], raw["account_rent_lamports"] = _rent.rent_labels(tx, keys, wallet)
    else:
        raw["ata_rent_refund_lamports"] = _rent.ata_close_refund(tx, keys, wallet)
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
                tx=tx,
                keys=keys,
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
