"""``SellEvent`` — the PumpSwap fill, as the chain reports it (T4.29a).

Same Anchor ``#[event_cpi]`` self-CPI convention ``hunter_exchanges.pumpfun
.trade_event`` already decodes (the event-CPI tag ``e445a52e51cb9a1d`` is an
Anchor-wide constant, ``sha256("global:emit_cpi")[:8]`` — identical in every
program using the feature, reused here rather than redefined). Discriminator
and the 26-field layout are read from the same on-chain IDL ``decode.py``
cites (all fixed-size fields — no strings or vectors, unlike the bonding
curve's ``TradeEvent``). T4.29a had **not** checked it against a real
``SellEvent`` (``.claude/state/notes-T4.29a.md`` "not proven"); T4.8e did, with four real
sells of 2026-10-05.

**Layout of 2026-10-02 (T4.8e).** The PumpSwap program redeployed that day (slot 452654882,
15:47:07Z) emits 49 bytes after those 26 fields: 41 declared by the GitHub IDL
(``virtual_quote_reserves`` i128, ``can_boost`` bool, ``base_supply`` u64,
``holder_rewards_bps`` u64, ``holder_rewards`` u64 — decoded as fields) and 8 named in no IDL
(:attr:`SellEvent.trailing_u64`, reported, **never summed**: the money is
``user_quote_amount_out`` and the payer's real balance delta). 4 of 4 real events (441-byte
bodies) were refused before. The tail is validated after the last known field; the only
trailing lengths accepted are 0 (the 26-field layout) and 49 — anything else, including the
IDL's 41 without the unnamed 8, is refused (an unknown layout is not a fill).
"""

from __future__ import annotations

import struct
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any, cast

from hunter_exchanges.pumpfun.solana_codec import b58decode, b58encode
from hunter_exchanges.pumpfun.trade_event import EVENT_CPI_TAG
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID

__all__ = [
    "LAYOUT_IDL_26",
    "LAYOUT_TRAILING_U64",
    "SELL_EVENT_DISCRIMINATOR",
    "SellEvent",
    "decode_sell_event",
    "sell_events_from_transaction",
]

SELL_EVENT_DISCRIMINATOR = bytes([62, 47, 55, 10, 165, 3, 220, 42])
LAYOUT_IDL_26 = "idl-26-fields"
"""The T4.29a layout: 26 fields, 392 bytes with the discriminator, nothing after."""
LAYOUT_TRAILING_U64 = "2026-10-02/idl_extension_trailing_u64"
"""26 fields + 41 declared bytes + one unnamed ``u64`` (441 bytes): the 2026-10-02 redeploy."""
_IDL_EXTENSION = 41
_UNNAMED_TAIL = 8


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
    layout: str = LAYOUT_IDL_26
    virtual_quote_reserves: int | None = None
    """i128 (signed, beyond 64 bits). ``None`` — never ``0`` — on the 26-field layout."""
    can_boost: bool | None = None
    base_supply: int | None = None
    holder_rewards_basis_points: int | None = None
    holder_rewards: int | None = None
    """``0`` on the four real fills of 2026-10-05. Reported, not summed."""
    trailing_u64: int | None = None
    """The unnamed ``u64`` after the IDL's extension (seen ``0 … 9 915 553``). Reported, **never**
    summed or interpreted; ``None`` on the 26-field layout, so a real ``0`` is a reading."""

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

    def i128(self) -> int:
        return int.from_bytes(self.take(16), "little", signed=True)

    def boolean(self) -> bool:
        byte = self.take(1)[0]
        if byte not in (0, 1):
            raise ValueError("SellEvent boolean is not 0/1")
        return bool(byte)


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
    if trailing not in (0, _IDL_EXTENSION + _UNNAMED_TAIL):
        raise ValueError(f"SellEvent has {trailing} trailing bytes")
    event = SellEvent(
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
    if not trailing:
        return event
    return replace(
        event,
        layout=LAYOUT_TRAILING_U64,
        virtual_quote_reserves=r.i128(),
        can_boost=r.boolean(),
        base_supply=r.u64(),
        holder_rewards_basis_points=r.u64(),
        holder_rewards=r.u64(),
        trailing_u64=r.u64(),
    )


def _obj(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _seq(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _event_payloads(transaction: dict[str, Any]) -> Iterable[bytes]:
    meta = _obj(transaction.get("meta"))
    message = _obj(_obj(transaction.get("transaction")).get("message"))
    keys: list[Any] = [*_seq(message.get("accountKeys"))]  # a copy: never extend the caller's list
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
