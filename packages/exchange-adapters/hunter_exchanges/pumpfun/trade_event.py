"""``TradeEvent`` — the fill, as the chain reports it (``docs/RISK_ENGINE_MEME.md`` §9.6).

The pump program emits events through Anchor's ``#[event_cpi]``: a self-CPI
whose instruction data is ``e445a52e51cb9a1d`` (the event-CPI tag) followed by
the event's own 8-byte discriminator and its Borsh body. The same bytes also
appear base64-encoded in ``meta.logMessages`` as ``Program data: …``. This
module decodes the body field by field in the exact order of the official IDL
(``docs/PUMPFUN-ONCHAIN.md`` §1.4; T4.8 checked the layout against a real
mainnet sell, ``tests/fixtures/pumpfun/rpc_tx_probe_raw.json``: 359 bytes
consumed of 359).

What a fill costs comes **from the event**, never from a constant:
``fee`` (protocol, ``fee_basis_points``), ``creator_fee`` and — for cashback
coins — ``cashback``, which the T4.8 balance reconciliation proved is also
deducted from the trader's SOL (``user`` delta = ``sol_amount − fee − cashback
− network fee − tip``, lamport-exact) even though ``creator_fee`` reads 0.
"""

from __future__ import annotations

import base64
import struct
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast

from hunter_exchanges.pumpfun.solana_codec import b58decode, b58encode

__all__ = [
    "EVENT_CPI_TAG",
    "TRADE_EVENT_DISCRIMINATOR",
    "TradeEvent",
    "decode_trade_event",
    "trade_events_from_transaction",
]

EVENT_CPI_TAG = bytes.fromhex("e445a52e51cb9a1d")
TRADE_EVENT_DISCRIMINATOR = bytes.fromhex("bddb7fd34ee661ee")
_LOG_PREFIX = "Program data: "


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
    if r.off != len(raw):
        raise ValueError(f"TradeEvent has {len(raw) - r.off} trailing bytes")
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
    )


def _obj(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _seq(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _event_payloads(transaction: dict[str, Any], program_id: str) -> Iterable[bytes]:
    """Event bytes from the inner instructions first (structured), then from the logs
    (the same bytes, base64) when the RPC did not return inner instructions."""
    meta = _obj(transaction.get("meta"))
    message = _obj(_obj(transaction.get("transaction")).get("message"))
    keys: list[Any] = _seq(message.get("accountKeys"))
    loaded = _obj(meta.get("loadedAddresses"))
    keys += _seq(loaded.get("writable")) + _seq(loaded.get("readonly"))
    if meta.get("innerInstructions") is not None:
        # Structured path: the program that emitted each event is known.
        for inner in _seq(meta.get("innerInstructions")):
            for ix_any in _seq(_obj(inner).get("instructions")):
                ix = _obj(ix_any)
                index: Any = ix.get("programIdIndex")
                if not isinstance(index, int) or index >= len(keys) or keys[index] != program_id:
                    continue
                data = b58decode(str(ix.get("data", "")))
                if data[:8] == EVENT_CPI_TAG and data[8:16] == TRADE_EVENT_DISCRIMINATOR:
                    yield data
        return
    # Logs-only path (RPC without inner instructions): the discriminator is the
    # only attribution available, so ``program_id`` cannot be enforced here.
    for line in _seq(meta.get("logMessages")):
        if isinstance(line, str) and line.startswith(_LOG_PREFIX):
            try:
                data = base64.b64decode(line[len(_LOG_PREFIX) :], validate=True)
            except ValueError:
                continue
            if data[:8] == TRADE_EVENT_DISCRIMINATOR:
                yield data


def trade_events_from_transaction(
    transaction: dict[str, Any], *, program_id: str
) -> tuple[TradeEvent, ...]:
    """Every ``TradeEvent`` the pump program emitted in a ``getTransaction`` result
    (``encoding: json``). A failed transaction (``meta.err`` set) yields nothing: a
    reverted event is not a fill."""
    if _obj(transaction.get("meta")).get("err") is not None:
        return ()
    return tuple(decode_trade_event(raw) for raw in _event_payloads(transaction, program_id))
