"""``SellEvent`` — the PumpSwap fill, as the chain reports it (T4.29a).

Same Anchor ``#[event_cpi]`` self-CPI convention ``hunter_exchanges.pumpfun
.trade_event`` already decodes (the event-CPI tag ``e445a52e51cb9a1d`` is an
Anchor-wide constant, ``sha256("global:emit_cpi")[:8]`` — identical in every
program using the feature, reused here rather than redefined). Discriminator
and the 26-field layout are read from the same on-chain IDL ``decode.py``
cites (all fixed-size fields — no strings or vectors, unlike the bonding
curve's ``TradeEvent``). **Not yet checked against a real ``SellEvent``**: no
wallet exists in this task to produce a real PumpSwap sell fill (see
``.claude/state/notes-T4.29a.md`` "not proven"); the field order and sizes
come only from the IDL.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast

from hunter_exchanges.pumpfun.solana_codec import b58decode, b58encode
from hunter_exchanges.pumpfun.trade_event import EVENT_CPI_TAG
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID

__all__ = [
    "SELL_EVENT_DISCRIMINATOR",
    "SellEvent",
    "decode_sell_event",
    "sell_events_from_transaction",
]

SELL_EVENT_DISCRIMINATOR = bytes([62, 47, 55, 10, 165, 3, 220, 42])


@dataclass(frozen=True, slots=True)
class SellEvent:
    timestamp: int
    base_amount_in: int
    min_quote_amount_out: int
    user_base_token_reserves: int
    user_quote_token_reserves: int
    pool_base_token_reserves: int
    pool_quote_token_reserves: int
    quote_amount_out: int
    lp_fee_basis_points: int
    lp_fee: int
    protocol_fee_basis_points: int
    protocol_fee: int
    quote_amount_out_without_lp_fee: int
    user_quote_amount_out: int
    pool: str
    user: str
    user_base_token_account: str
    user_quote_token_account: str
    protocol_fee_recipient: str
    protocol_fee_recipient_token_account: str
    coin_creator: str
    coin_creator_fee_basis_points: int
    coin_creator_fee: int
    cashback_fee_basis_points: int
    cashback: int
    buyback_fee_basis_points: int
    buyback_fee: int

    @property
    def net_proceeds(self) -> int:
        """What actually lands in the user's WSOL account — the event's own
        final number, all fees already taken out (mirrors ``TradeEvent
        .sell_net_proceeds`` but read directly instead of re-derived)."""
        return self.user_quote_amount_out


class _Reader:
    def __init__(self, raw: bytes, offset: int) -> None:
        self.raw = raw
        self.off = offset

    def take(self, n: int) -> bytes:
        if self.off + n > len(self.raw):
            raise ValueError("SellEvent truncated")
        chunk = self.raw[self.off : self.off + n]
        self.off += n
        return chunk

    def pubkey(self) -> str:
        return b58encode(self.take(32))

    def u64(self) -> int:
        return struct.unpack("<Q", self.take(8))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.take(8))[0]


def decode_sell_event(raw: bytes) -> SellEvent:
    if raw[:8] == EVENT_CPI_TAG:
        raw = raw[8:]
    if raw[:8] != SELL_EVENT_DISCRIMINATOR:
        raise ValueError("not a SellEvent (discriminator mismatch)")
    r = _Reader(raw, 8)
    timestamp = r.i64()
    base_amount_in, min_quote_amount_out = r.u64(), r.u64()
    user_base_reserves, user_quote_reserves = r.u64(), r.u64()
    pool_base_reserves, pool_quote_reserves = r.u64(), r.u64()
    quote_amount_out = r.u64()
    lp_bps, lp_fee = r.u64(), r.u64()
    protocol_bps, protocol_fee = r.u64(), r.u64()
    quote_without_lp_fee = r.u64()
    user_quote_amount_out = r.u64()
    pool, user = r.pubkey(), r.pubkey()
    user_base_ta, user_quote_ta = r.pubkey(), r.pubkey()
    protocol_recipient, protocol_recipient_ta = r.pubkey(), r.pubkey()
    coin_creator = r.pubkey()
    coin_creator_bps, coin_creator_fee = r.u64(), r.u64()
    cashback_bps, cashback = r.u64(), r.u64()
    buyback_bps, buyback_fee = r.u64(), r.u64()
    trailing = len(raw) - r.off
    if trailing != 0:
        raise ValueError(f"SellEvent has {trailing} trailing bytes")
    return SellEvent(
        timestamp=timestamp,
        base_amount_in=base_amount_in,
        min_quote_amount_out=min_quote_amount_out,
        user_base_token_reserves=user_base_reserves,
        user_quote_token_reserves=user_quote_reserves,
        pool_base_token_reserves=pool_base_reserves,
        pool_quote_token_reserves=pool_quote_reserves,
        quote_amount_out=quote_amount_out,
        lp_fee_basis_points=lp_bps,
        lp_fee=lp_fee,
        protocol_fee_basis_points=protocol_bps,
        protocol_fee=protocol_fee,
        quote_amount_out_without_lp_fee=quote_without_lp_fee,
        user_quote_amount_out=user_quote_amount_out,
        pool=pool,
        user=user,
        user_base_token_account=user_base_ta,
        user_quote_token_account=user_quote_ta,
        protocol_fee_recipient=protocol_recipient,
        protocol_fee_recipient_token_account=protocol_recipient_ta,
        coin_creator=coin_creator,
        coin_creator_fee_basis_points=coin_creator_bps,
        coin_creator_fee=coin_creator_fee,
        cashback_fee_basis_points=cashback_bps,
        cashback=cashback,
        buyback_fee_basis_points=buyback_bps,
        buyback_fee=buyback_fee,
    )


def _obj(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _seq(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _event_payloads(transaction: dict[str, Any]) -> Iterable[bytes]:
    meta = _obj(transaction.get("meta"))
    message = _obj(_obj(transaction.get("transaction")).get("message"))
    keys: list[Any] = _seq(message.get("accountKeys"))
    loaded = _obj(meta.get("loadedAddresses"))
    keys += _seq(loaded.get("writable")) + _seq(loaded.get("readonly"))
    for inner in _seq(meta.get("innerInstructions")):
        for ix_any in _seq(_obj(inner).get("instructions")):
            ix = _obj(ix_any)
            index: Any = ix.get("programIdIndex")
            if (
                not isinstance(index, int)
                or index >= len(keys)
                or keys[index] != PUMPSWAP_PROGRAM_ID
            ):
                continue
            data = b58decode(str(ix.get("data", "")))
            if data[:8] == EVENT_CPI_TAG and data[8:16] == SELL_EVENT_DISCRIMINATOR:
                yield data


def sell_events_from_transaction(transaction: dict[str, Any]) -> tuple[SellEvent, ...]:
    """Every ``SellEvent`` the PumpSwap program emitted in a ``getTransaction``
    result. A failed transaction yields nothing."""
    if _obj(transaction.get("meta")).get("err") is not None:
        return ()
    return tuple(decode_sell_event(raw) for raw in _event_payloads(transaction))
