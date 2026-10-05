"""``TradeEvent`` — the fill, as the chain reports it (``docs/RISK_ENGINE_MEME.md`` §9.6): the
byte codec. Split out of ``trade_event.py`` (T4.8e) only to fit the file-size budget; every name
here is re-exported from there, which stays the import path.

The pump program emits events through Anchor's ``#[event_cpi]``: a self-CPI
whose instruction data is ``e445a52e51cb9a1d`` (the event-CPI tag) followed by
the event's own 8-byte discriminator and its Borsh body. The same bytes also
appear base64-encoded in ``meta.logMessages`` as ``Program data: …``. This
module decodes the body field by field in the exact order of the official IDL
(``docs/PUMPFUN-ONCHAIN.md`` §1.4; T4.8 checked the layout against a real
mainnet sell, ``tests/fixtures/pumpfun/rpc_tx_probe_raw.json``: 359 bytes
consumed of 359).

**Layout of 2026-09-12 (T4.8b).** The program deployed that afternoon (slot
446462760) appends two ``u64`` — ``holder_rewards_bps``, ``holder_rewards`` — after
``real_quote_reserves`` (375 bytes; real sell ``t48b_rpc_tx_sell_raw.json``, real
router buy ``t48b_rpc_tx_buy_router_v2_raw.json``). They are fields of
:class:`TradeEvent`; an event of the older 359-byte layout decodes with both at
``0`` and ``layout`` naming it, so the pre-upgrade fixtures stay readable.

**Layout of 2026-10-02 (T4.8e).** The redeploy of that day (slot 452654932, 15:47:21Z)
appends one more ``u64``, named in no IDL (the on-chain IDL was not republished; the GitHub
one does not list it), values seen ``0 … 39 743 440``: 22 of 22 real events carry it, and
``decode_trade_event`` refused all of them until T4.8e. The tail is validated **after** the
variable-length fields (``ix_name``, ``shareholders``), never by total length — the body is
382 bytes for a ``buy`` and 383 for a ``sell`` only because ``ix_name`` differs. It is
exposed as :attr:`TradeEvent.trailing_u64` and, its meaning being unknown, **never summed**.
Any other trailing length is refused: an unknown layout is not a fill.

What a fill costs comes **from the event**, never from a constant:
``fee`` (protocol, ``fee_basis_points``), ``creator_fee`` and — for cashback
coins — ``cashback``, which the T4.8 balance reconciliation proved is also
deducted from the trader's SOL (``user`` delta = ``sol_amount − fee − cashback
− network fee − tip``, lamport-exact) even though ``creator_fee`` reads 0.
``holder_rewards`` read ``0`` on every fill of 2026-09-12 (three sells, one buy);
whether a non-zero value is a split of ``fee`` (as ``buyback_fee`` is) or one more
deduction is **not** established, so it is reported and not summed — the
executor's ledger uses the payer's real balance delta (``docs/RISK_ENGINE_MEME.md``
§9.6) and names the gap to the event arithmetic.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from hunter_exchanges.pumpfun.solana_codec import b58encode

__all__ = [
    "EVENT_CPI_TAG",
    "LAYOUT_HOLDER_REWARDS",
    "LAYOUT_PRE_HOLDER_REWARDS",
    "LAYOUT_TRAILING_U64",
    "TRADE_EVENT_DISCRIMINATOR",
    "TradeEvent",
    "decode_trade_event",
]

EVENT_CPI_TAG = bytes.fromhex("e445a52e51cb9a1d")
TRADE_EVENT_DISCRIMINATOR = bytes.fromhex("bddb7fd34ee661ee")
LAYOUT_TRAILING_U64 = "2026-10-02/trailing_u64"
"""35 fields, 24 trailing bytes after the variable fields: the program redeployed on
2026-10-02 (slot 452654932) — the holder-rewards pair plus one unnamed ``u64``."""
LAYOUT_HOLDER_REWARDS = "2026-09-12/holder_rewards"
"""34 fields, 375 bytes: the program deployed on 2026-09-12 (slot 446462760)."""
LAYOUT_PRE_HOLDER_REWARDS = "pre-2026-09-12"
"""32 fields, 359 bytes: the T4.8 fixtures (morning of 2026-09-12)."""
_HOLDER_REWARDS_TAIL = 16
_UNNAMED_TAIL = 8


@dataclass(frozen=True, slots=True)
class TradeEvent:
    mint: str
    sol_amount: int
    token_amount: int
    is_buy: bool
    user: str
    timestamp: int
    virtual_sol_reserves: int
    virtual_token_reserves: int
    real_sol_reserves: int
    real_token_reserves: int
    fee_recipient: str
    fee_basis_points: int
    fee: int
    creator: str
    creator_fee_basis_points: int
    creator_fee: int
    track_volume: bool
    total_unclaimed_tokens: int
    total_claimed_tokens: int
    current_sol_volume: int
    last_update_timestamp: int
    ix_name: str
    mayhem_mode: bool
    cashback_fee_basis_points: int
    cashback: int
    buyback_fee_basis_points: int
    buyback_fee: int
    shareholders: tuple[tuple[str, int], ...]
    quote_mint: str
    quote_amount: int
    virtual_quote_reserves: int
    real_quote_reserves: int
    holder_rewards_basis_points: int
    """Appended by the program deployed on 2026-09-12 (``holder_rewards_bps``,
    ``holder_rewards``: two ``u64``). ``0`` on every fill recorded that day and on
    an event of the older layout (``layout`` says which). Not summed into the
    trader's cost here: the wallet's real balance delta is the ledger's truth."""
    holder_rewards: int
    layout: str = LAYOUT_HOLDER_REWARDS
    trailing_u64: int | None = None
    """Appended by the program redeployed on 2026-10-02: one ``u64`` named in no IDL
    (seen ``0 … 39 743 440``). Reported, **never** summed or interpreted — ``None`` on an
    event of an earlier layout (``layout`` says which), so a real ``0`` is a reading."""

    @property
    def sol_deducted_from_user(self) -> int:
        """Lamports the trader gives up beyond ``sol_amount``: protocol fee, creator fee
        and cashback — all three leave the wallet (reconciled lamport-exact in T4.8)."""
        return self.fee + self.creator_fee + self.cashback

    @property
    def buy_total_cost(self) -> int:
        """A buy pays ``sol_amount`` into the curve plus every deduction."""
        return self.sol_amount + self.sol_deducted_from_user

    @property
    def sell_net_proceeds(self) -> int:
        """A sell receives ``sol_amount`` from the curve minus every deduction."""
        return self.sol_amount - self.sol_deducted_from_user


class _Reader:
    def __init__(self, raw: bytes, offset: int) -> None:
        self.raw = raw
        self.off = offset

    def take(self, n: int) -> bytes:
        if self.off + n > len(self.raw):
            raise ValueError("TradeEvent truncated")
        chunk = self.raw[self.off : self.off + n]
        self.off += n
        return chunk

    def pubkey(self) -> str:
        return b58encode(self.take(32))

    def u64(self) -> int:
        return struct.unpack("<Q", self.take(8))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.take(8))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.take(2))[0]

    def boolean(self) -> bool:
        byte = self.take(1)[0]
        if byte not in (0, 1):
            raise ValueError("TradeEvent boolean is not 0/1")
        return bool(byte)

    def string(self) -> str:
        return self.take(self.u32()).decode("utf-8")


def decode_trade_event(raw: bytes) -> TradeEvent:
    """Decode ``TradeEvent`` bytes. Accepts the body with or without the event-CPI tag."""
    if raw[:8] == EVENT_CPI_TAG:
        raw = raw[8:]
    if raw[:8] != TRADE_EVENT_DISCRIMINATOR:
        raise ValueError("not a TradeEvent (discriminator mismatch)")
    r = _Reader(raw, 8)
    mint = r.pubkey()
    sol_amount = r.u64()
    token_amount = r.u64()
    is_buy = r.boolean()
    user = r.pubkey()
    timestamp = r.i64()
    vsol, vtok, rsol, rtok = r.u64(), r.u64(), r.u64(), r.u64()
    fee_recipient = r.pubkey()
    fee_bps, fee = r.u64(), r.u64()
    creator = r.pubkey()
    creator_fee_bps, creator_fee = r.u64(), r.u64()
    track_volume = r.boolean()
    total_unclaimed, total_claimed, current_sol_volume = r.u64(), r.u64(), r.u64()
    last_update = r.i64()
    ix_name = r.string()
    mayhem_mode = r.boolean()
    cashback_bps, cashback, buyback_bps, buyback_fee = r.u64(), r.u64(), r.u64(), r.u64()
    shareholders = tuple((r.pubkey(), r.u16()) for _ in range(r.u32()))
    quote_mint = r.pubkey()
    quote_amount, vquote, rquote = r.u64(), r.u64(), r.u64()
    # Validated after every variable-length field, never by total length (T4.8e).
    trailing = len(raw) - r.off
    holder_rewards_bps = holder_rewards = 0
    trailing_u64: int | None = None
    if trailing == 0:
        # The layout the program emitted before its 2026-09-12 upgrade (T4.8 fixtures).
        layout = LAYOUT_PRE_HOLDER_REWARDS
    elif trailing == _HOLDER_REWARDS_TAIL:
        holder_rewards_bps, holder_rewards, layout = r.u64(), r.u64(), LAYOUT_HOLDER_REWARDS
    elif trailing == _HOLDER_REWARDS_TAIL + _UNNAMED_TAIL:
        holder_rewards_bps, holder_rewards = r.u64(), r.u64()
        trailing_u64, layout = r.u64(), LAYOUT_TRAILING_U64
    else:
        raise ValueError(f"TradeEvent has {trailing} trailing bytes")
    return TradeEvent(
        mint=mint,
        sol_amount=sol_amount,
        token_amount=token_amount,
        is_buy=is_buy,
        user=user,
        timestamp=timestamp,
        virtual_sol_reserves=vsol,
        virtual_token_reserves=vtok,
        real_sol_reserves=rsol,
        real_token_reserves=rtok,
        fee_recipient=fee_recipient,
        fee_basis_points=fee_bps,
        fee=fee,
        creator=creator,
        creator_fee_basis_points=creator_fee_bps,
        creator_fee=creator_fee,
        track_volume=track_volume,
        total_unclaimed_tokens=total_unclaimed,
        total_claimed_tokens=total_claimed,
        current_sol_volume=current_sol_volume,
        last_update_timestamp=last_update,
        ix_name=ix_name,
        mayhem_mode=mayhem_mode,
        cashback_fee_basis_points=cashback_bps,
        cashback=cashback,
        buyback_fee_basis_points=buyback_bps,
        buyback_fee=buyback_fee,
        shareholders=shareholders,
        quote_mint=quote_mint,
        quote_amount=quote_amount,
        virtual_quote_reserves=vquote,
        real_quote_reserves=rquote,
        holder_rewards_basis_points=holder_rewards_bps,
        holder_rewards=holder_rewards,
        layout=layout,
        trailing_u64=trailing_u64,
    )
