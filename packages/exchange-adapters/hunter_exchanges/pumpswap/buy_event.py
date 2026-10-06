"""``BuyEvent`` — the PumpSwap buy fill, as the chain reports it (wave 1a of H-030).

Twin of :mod:`hunter_exchanges.pumpswap.sell_event`: the same Anchor ``#[event_cpi]`` self-CPI
(event-CPI tag ``e445a52e51cb9a1d`` + the event's 8-byte discriminator + a Borsh body). It had no
decoder until now although it is 36 % of the program's swaps (wave-0 probe, 05/10/2026: 118 of 268
swap events/s).

**Layout.** Field order is the one of the program's own IDL (GitHub head, ``BuyEvent``): 34 fields up
to ``buyback_fee`` — the variable ``ix_name`` string sits in the middle — then the 41 bytes the
IDL declares after them (``virtual_quote_reserves`` i128, ``can_boost``, ``base_supply``,
``holder_rewards_bps``, ``holder_rewards``) and, since the redeploy of 2026-10-02 (15:47Z), one more
``u64`` named in no IDL (:attr:`BuyEvent.trailing_u64`, reported, **never summed**). 48 of 48 real
post-upgrade buys read on 2026-10-05 carried exactly that 49-byte tail. It is validated after the last
field, never by total length (the body is 497 bytes for ``buy`` and 512 for ``buy_exact_quote_in``
only because ``ix_name`` differs). Any other tail is refused, **including none at all**: the
pre-upgrade layout was never seen by this project, and an unproven layout is not a fill.

**What the fields mean (checked against the chain, not assumed).**

* ``pool`` and ``user`` are accounts 0 and 1 of the program's swap instruction, also when a router
  calls it (7 of 7 real fixtures, ``tests/unit/test_pumpswap_buy_event.py``).
* ``pool_*_token_reserves`` are the reserves **before** the trade: the next event of the same pool
  shows ``base - base_amount_out`` and ``quote + quote_amount_in_with_lp_fee`` (the LP fee stays in
  the pool). Pump's curve events are the opposite (after the trade); do not mix them up.
* The pool vault receives exactly ``quote_amount_in_with_lp_fee``; the protocol, creator (and
  cashback) fees go to other accounts. So the user pays ``quote_amount_in_with_lp_fee + protocol_fee
  + coin_creator_fee + cashback`` (:attr:`BuyEvent.total_quote_paid`) and the quote that priced the
  base is ``quote_amount_in_with_lp_fee - lp_fee`` (:attr:`BuyEvent.net_quote_in`). ``holder_rewards``
  and ``buyback_fee`` are splits of a fee, not extra deductions.
* **Field names lie on ``buy_exact_quote_in``.** There the program writes the total the user pays
  into ``quote_amount_in`` and the net quote into ``user_quote_amount_in`` — the opposite of
  ``buy`` (confirmed on the 4 ``buy_exact_quote_in`` fixtures by the pool-vault delta, next to 3 ``buy`` ones;
  the set check holds on every one of the 48 real buys read). Both derived quantities above
  are computed from the fields whose meaning does not move, and :attr:`BuyEvent.money_conserves`
  checks the event's own pair against them (as a set, so it holds for either instruction) — an event
  whose money does not close is not to be turned into a fill.
* **Cashback on a buy is unverified**: no real buy of the 48 read had ``cashback != 0``. It is
  counted as a fee (as on the curve and on the PumpSwap sell, where it is proven); if that is wrong
  the event fails :attr:`~BuyEvent.money_conserves` and is reported, not guessed.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast

from hunter_exchanges.pumpfun.solana_codec import b58decode, b58encode
from hunter_exchanges.pumpfun.trade_event_codec import EVENT_CPI_TAG
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID

__all__ = [
    "BUY_EVENT_DISCRIMINATOR",
    "LAYOUT_TRAILING_U64",
    "BuyEvent",
    "BuyEventError",
    "buy_events_from_transaction",
    "decode_buy_event",
]

BUY_EVENT_DISCRIMINATOR = bytes([103, 244, 82, 31, 44, 245, 119, 119])
LAYOUT_TRAILING_U64 = "2026-10-02/idl_extension_trailing_u64"
"""34 IDL fields + the 41 declared bytes + one unnamed ``u64``: the redeploy of 2026-10-02."""
_TAIL = 41 + 8


class BuyEventError(ValueError):
    """A ``BuyEvent`` payload this decoder refuses: wrong discriminator, truncated, a boolean that
    is not 0/1, an ``ix_name`` that is not UTF-8, or a tail length that is not a layout seen on
    chain. A ``ValueError`` so callers that already catch the sibling decoders' errors keep working."""


@dataclass(frozen=True, slots=True)
class BuyEvent:
    timestamp: int
    base_amount_out: int
    max_quote_amount_in: int
    user_base_token_reserves: int
    user_quote_token_reserves: int
    pool_base_token_reserves: int
    """Pool reserves BEFORE this trade (see the module docstring)."""
    pool_quote_token_reserves: int
    quote_amount_in: int
    """Net quote on ``buy``, the TOTAL paid on ``buy_exact_quote_in``: use :attr:`net_quote_in` /
    :attr:`total_quote_paid`, not this name."""
    lp_fee_basis_points: int
    lp_fee: int
    protocol_fee_basis_points: int
    protocol_fee: int
    quote_amount_in_with_lp_fee: int
    user_quote_amount_in: int
    """The total paid on ``buy``, the net quote on ``buy_exact_quote_in``."""
    pool: str
    user: str
    user_base_token_account: str
    user_quote_token_account: str
    protocol_fee_recipient: str
    protocol_fee_recipient_token_account: str
    coin_creator: str
    coin_creator_fee_basis_points: int
    coin_creator_fee: int
    track_volume: bool
    total_unclaimed_tokens: int
    total_claimed_tokens: int
    current_sol_volume: int
    last_update_timestamp: int
    min_base_amount_out: int
    ix_name: str
    cashback_fee_basis_points: int
    cashback: int
    buyback_fee_basis_points: int
    buyback_fee: int
    virtual_quote_reserves: int
    """i128 (signed, beyond 64 bits)."""
    can_boost: bool
    base_supply: int
    holder_rewards_basis_points: int
    holder_rewards: int
    """Reported, **not** summed into the cost (a split of a fee: the conservation below closes
    without it on every real event, including those with ``holder_rewards != 0``)."""
    trailing_u64: int
    """The unnamed ``u64`` after the IDL's extension. Reported, **never** summed or interpreted."""
    layout: str = LAYOUT_TRAILING_U64

    @property
    def net_quote_in(self) -> int:
        """The quote that priced the base: what reached the pool minus the LP fee that stays there."""
        return self.quote_amount_in_with_lp_fee - self.lp_fee

    @property
    def fee_total(self) -> int:
        """Every fee the event declares as paid by the trader (LP, protocol, creator, cashback)."""
        return self.lp_fee + self.protocol_fee + self.coin_creator_fee + self.cashback

    @property
    def total_quote_paid(self) -> int:
        """What leaves the user's quote account: the pool's quote plus the fees paid on top."""
        return self.net_quote_in + self.fee_total

    @property
    def money_conserves(self) -> bool:
        """The event's own two quote fields are exactly ``{net_quote_in, total_quote_paid}`` — in
        either order, because ``buy`` and ``buy_exact_quote_in`` write them swapped."""
        return {self.quote_amount_in, self.user_quote_amount_in} == {
            self.net_quote_in,
            self.total_quote_paid,
        }


class _Reader:
    def __init__(self, raw: bytes, offset: int) -> None:
        self.raw = raw
        self.off = offset

    def take(self, n: int) -> bytes:
        if n < 0 or self.off + n > len(self.raw):
            raise BuyEventError("BuyEvent truncated")
        chunk = self.raw[self.off : self.off + n]
        self.off += n
        return chunk

    def pubkey(self) -> str:
        return b58encode(self.take(32))

    def u64(self) -> int:
        return cast(int, struct.unpack("<Q", self.take(8))[0])

    def i64(self) -> int:
        return cast(int, struct.unpack("<q", self.take(8))[0])

    def i128(self) -> int:
        return int.from_bytes(self.take(16), "little", signed=True)

    def boolean(self) -> bool:
        byte = self.take(1)[0]
        if byte not in (0, 1):
            raise BuyEventError("BuyEvent boolean is not 0/1")
        return bool(byte)

    def string(self) -> str:
        length = cast(int, struct.unpack("<I", self.take(4))[0])
        try:
            return self.take(length).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BuyEventError("BuyEvent ix_name is not UTF-8") from exc


def decode_buy_event(raw: bytes) -> BuyEvent:
    """Decode ``BuyEvent`` bytes, with or without the event-CPI tag. Raises :class:`BuyEventError`
    for anything that is not exactly the layout of 2026-10-02."""
    if raw[:8] == EVENT_CPI_TAG:
        raw = raw[8:]
    if raw[:8] != BUY_EVENT_DISCRIMINATOR:
        raise BuyEventError("not a BuyEvent (discriminator mismatch)")
    r = _Reader(raw, 8)
    timestamp = r.i64()
    (base_out, max_quote, user_base_res, user_quote_res, pool_base_res, pool_quote_res) = (
        r.u64() for _ in range(6)
    )
    quote_in, lp_bps, lp_fee, protocol_bps, protocol_fee = (r.u64() for _ in range(5))
    quote_in_with_lp_fee, user_quote_in = r.u64(), r.u64()
    pool, user, user_base_ta, user_quote_ta = (r.pubkey() for _ in range(4))
    protocol_recipient, protocol_recipient_ta, coin_creator = (r.pubkey() for _ in range(3))
    creator_bps, creator_fee = r.u64(), r.u64()
    track_volume = r.boolean()
    unclaimed, claimed, current_sol_volume = r.u64(), r.u64(), r.u64()
    last_update, min_base_out = r.i64(), r.u64()
    ix_name = r.string()
    cashback_bps, cashback, buyback_bps, buyback_fee = (r.u64() for _ in range(4))
    trailing = len(raw) - r.off
    if trailing != _TAIL:
        raise BuyEventError(f"BuyEvent has {trailing} trailing bytes")
    return BuyEvent(
        timestamp=timestamp,
        base_amount_out=base_out,
        max_quote_amount_in=max_quote,
        user_base_token_reserves=user_base_res,
        user_quote_token_reserves=user_quote_res,
        pool_base_token_reserves=pool_base_res,
        pool_quote_token_reserves=pool_quote_res,
        quote_amount_in=quote_in,
        lp_fee_basis_points=lp_bps,
        lp_fee=lp_fee,
        protocol_fee_basis_points=protocol_bps,
        protocol_fee=protocol_fee,
        quote_amount_in_with_lp_fee=quote_in_with_lp_fee,
        user_quote_amount_in=user_quote_in,
        pool=pool,
        user=user,
        user_base_token_account=user_base_ta,
        user_quote_token_account=user_quote_ta,
        protocol_fee_recipient=protocol_recipient,
        protocol_fee_recipient_token_account=protocol_recipient_ta,
        coin_creator=coin_creator,
        coin_creator_fee_basis_points=creator_bps,
        coin_creator_fee=creator_fee,
        track_volume=track_volume,
        total_unclaimed_tokens=unclaimed,
        total_claimed_tokens=claimed,
        current_sol_volume=current_sol_volume,
        last_update_timestamp=last_update,
        min_base_amount_out=min_base_out,
        ix_name=ix_name,
        cashback_fee_basis_points=cashback_bps,
        cashback=cashback,
        buyback_fee_basis_points=buyback_bps,
        buyback_fee=buyback_fee,
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
            if data[:8] == EVENT_CPI_TAG and data[8:16] == BUY_EVENT_DISCRIMINATOR:
                yield data


def buy_events_from_transaction(transaction: dict[str, Any]) -> tuple[BuyEvent, ...]:
    """Every ``BuyEvent`` the PumpSwap program emitted in a ``getTransaction`` result (any
    transaction version: only ``accountKeys``, ``loadedAddresses`` and ``innerInstructions`` are
    read). A failed transaction yields nothing; an undecodable event raises
    :class:`BuyEventError` rather than disappearing."""
    if _obj(transaction.get("meta")).get("err") is not None:
        return ()
    return tuple(decode_buy_event(raw) for raw in _event_payloads(transaction))
