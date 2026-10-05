"""From an approved PumpSwap sell to the bytes the submitter signs, and from a
landed transaction to the fill (T4.29a). Mirrors ``build.py``'s ``BuiltTrade``/
``FillRecord`` for the curve, one venue over: **sell only**, never a buy
(``docs/RISK_ENGINE_MEME.md`` §1 — PumpSwap is exit-only for a migrated
position).
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from hunter_exchanges.pumpfun.solana_codec import (
    TOKEN_PROGRAM_ID,
    associated_token_address,
    serialize_message,
)
from hunter_exchanges.pumpswap.decode import WSOL_MINT, GlobalConfig
from hunter_exchanges.pumpswap.pdas import user_volume_accumulator_address
from hunter_exchanges.pumpswap.quote import (
    PoolReserves,
    SellQuote,
    effective_quote_reserves,
    quote_pool_sell,
)
from hunter_exchanges.pumpswap.sell_event import SellEvent, sell_events_from_transaction
from hunter_exchanges.pumpswap.tx import PumpSwapSellIntent, build_sell_message
from hunter_exchanges.pumpswap.verify import ExecutionCaps, verify_pumpswap_sell_message
from hunter_meme_executor.chain import PoolRead

__all__ = [
    "BuiltPumpSwapSell",
    "PumpSwapFillRecord",
    "build_pumpswap_sell",
    "decode_pumpswap_fills",
    "pool_reserves_of",
]


_RNG = random.SystemRandom()


def pool_reserves_of(read: PoolRead) -> PoolReserves:
    return PoolReserves(
        base=read.base_token_amount,
        effective_quote=effective_quote_reserves(read.pool, read.quote_token_amount),
    )


@dataclass(frozen=True, slots=True)
class PumpSwapFillRecord:
    """The fill as the chain reported it — a decoded ``SellEvent`` when one is
    found, plus (the ledger's truth, same as the curve's ``FillRecord``) the
    payer's real SOL balance delta, which already reflects the WSOL unwrap."""

    signature: str
    slot: int
    block_time: datetime | None
    network_fee_lamports: int
    event: SellEvent | None = None
    payer_delta_lamports: int | None = None
    event_error: str | None = None
    """Why the ``SellEvent`` could not be decoded (T4.8e) — the record is then keyed on the
    payer's delta alone and says so; ``None`` when the event decoded or there was none."""
    wsol_ata_pre_lamports: int | None = None
    """T4.8f: what the payer's WSOL ATA held **before** the transaction (its own
    ``preBalances``: ``0`` when the sell created it, rent + leftover WSOL when it pre-existed).
    The closing ``CloseAccount`` pays all of it back to the payer, so it is in the payer's delta
    but is not this sale: kept out of :attr:`sell_net_lamports`. ``None`` when the ATA is not
    among the transaction's accounts (not our shape: nothing to subtract)."""
    cashback_init_lamports: int | None = None
    """T4.8f: what the payer **funded to create** the cashback ``user_volume_accumulator`` and/or
    its WSOL ATA in this sale (accounts absent before — ``pre == 0`` — and funded after), read from
    the transaction's own balances, never a constant. A wallet that never traded on PumpSwap pays
    it on its first cashback sell (simulated: 0 -> 1 346 200 on the accumulator). It stays inside
    :attr:`sell_net_lamports` (the real delta) but is *named*, so ``unexplained`` is not polluted."""

    @property
    def sell_net_lamports(self) -> int:
        """What this sale put in the wallet: the payer's real delta minus whatever the WSOL
        ATA already held (T4.8f) — a pre-existing ATA must not inflate the position's PnL."""
        if self.payer_delta_lamports is not None:
            return self.payer_delta_lamports - (self.wsol_ata_pre_lamports or 0)
        if self.event is not None:
            return self.event.net_proceeds - self.network_fee_lamports
        return 0

    @property
    def unexplained_lamports(self) -> int | None:
        """``sell_net − (user_quote_amount_out − network fee)``: ``0`` on a sell this executor
        builds and reads back; ``None`` without the event or the balances (T4.8f)."""
        if self.event is None or self.payer_delta_lamports is None:
            return None
        expected = self.event.user_quote_amount_out - self.network_fee_lamports
        return self.sell_net_lamports - expected + (self.cashback_init_lamports or 0)

    def as_json(self) -> dict[str, Any]:
        e = self.event
        return {
            "signature": self.signature,
            "slot": self.slot,
            "block_time": None if self.block_time is None else self.block_time.isoformat(),
            "venue": "pumpswap",
            "base_amount_in": None if e is None else e.base_amount_in,
            "quote_amount_out": None if e is None else e.quote_amount_out,
            "lp_fee": None if e is None else e.lp_fee,
            "protocol_fee": None if e is None else e.protocol_fee,
            "coin_creator_fee": None if e is None else e.coin_creator_fee,
            "user_quote_amount_out": None if e is None else e.user_quote_amount_out,
            "event_layout": None if e is None else e.layout,
            "event_trailing_u64": None if e is None else e.trailing_u64,
            "event_error": self.event_error,
            "network_fee_lamports": self.network_fee_lamports,
            "payer_delta_lamports": self.payer_delta_lamports,
            "wsol_ata_pre_lamports": self.wsol_ata_pre_lamports,
            "cashback_init_lamports": self.cashback_init_lamports,
            "unexplained_lamports": self.unexplained_lamports,
            "sell_net_lamports": self.sell_net_lamports,
        }


def _payer_delta(meta: dict[str, Any]) -> int | None:
    pre = cast(list[Any], meta.get("preBalances") or [])
    post = cast(list[Any], meta.get("postBalances") or [])
    if not pre or not post:
        return None
    try:
        return int(post[0]) - int(pre[0])
    except (TypeError, ValueError):
        return None


def _balances(
    transaction: dict[str, Any], meta: dict[str, Any]
) -> tuple[list[str], list[Any], list[Any]]:
    """``(account keys, preBalances, postBalances)`` of a ``getTransaction`` result."""
    message = cast(
        dict[str, Any], cast(dict[str, Any], transaction.get("transaction") or {}).get("message")
    )
    loaded = cast(dict[str, Any], meta.get("loadedAddresses") or {})
    keys = [
        *cast(list[str], (message or {}).get("accountKeys") or []),
        *cast(list[str], loaded.get("writable") or []),
        *cast(list[str], loaded.get("readonly") or []),
    ]
    return (
        keys,
        cast(list[Any], meta.get("preBalances") or []),
        cast(list[Any], meta.get("postBalances") or []),
    )


def _wsol_ata_pre_lamports(transaction: dict[str, Any], meta: dict[str, Any]) -> int | None:
    """What the payer's WSOL ATA held before the transaction, from its own ``preBalances``."""
    keys, pre, _post = _balances(transaction, meta)
    if not keys:
        return None
    ata = associated_token_address(keys[0], WSOL_MINT, token_program=TOKEN_PROGRAM_ID)
    if ata not in keys or keys.index(ata) >= len(pre):
        return None
    try:
        return int(pre[keys.index(ata)])
    except (TypeError, ValueError):
        return None


def _cashback_init_lamports(transaction: dict[str, Any], meta: dict[str, Any]) -> int | None:
    """Lamports the payer funded to create the cashback accumulator and/or its WSOL ATA in this
    transaction: each account among the transaction's accounts with ``pre == 0`` and a balance
    afterwards. ``None`` when none was created (or they are not among the accounts)."""
    keys, pre, post = _balances(transaction, meta)
    if not keys:
        return None
    accumulator = user_volume_accumulator_address(keys[0])
    accumulator_ata = associated_token_address(
        accumulator, WSOL_MINT, token_program=TOKEN_PROGRAM_ID
    )
    funded = 0
    for address in (accumulator, accumulator_ata):
        if address not in keys:
            continue
        i = keys.index(address)
        try:
            if i < len(pre) and i < len(post) and int(pre[i]) == 0 and int(post[i]) > 0:
                funded += int(post[i])
        except (TypeError, ValueError):
            continue
    return funded or None


def decode_pumpswap_fills(transaction: dict[str, Any]) -> list[PumpSwapFillRecord]:
    """``decode_fill`` for the submitter, PumpSwap edition. A landed
    transaction with no decodable ``SellEvent`` still yields one record keyed
    on the payer's balance delta — the WSOL unwrap makes that delta the
    honest net proceeds even when the event itself cannot be parsed. T4.8e: the
    fallback really runs now — the decode error is caught and carried in
    ``event_error`` (before, it escaped and a landed sell ended ``fill_decode_failed``).

    Contract of the fallback: the caller hands over the transaction of **our own order**,
    fetched by its recorded signature and routed by the order's venue (``exit_settle``) — a
    landed transaction with balances is booked as a sale here, never an arbitrary one."""
    meta = cast(dict[str, Any], transaction.get("meta") or {})
    if meta.get("err") is not None:
        return []
    tx = cast(dict[str, Any], transaction.get("transaction") or {})
    signatures = cast(list[Any], tx.get("signatures") or [""])
    block_time = transaction.get("blockTime")
    event_error: str | None = None
    try:
        events = sell_events_from_transaction(transaction)
    except ValueError as exc:  # an unknown layout is not a fill — the payer's delta is
        events, event_error = (), str(exc)
    delta = _payer_delta(meta)
    if not events and delta is None:
        return []
    record = PumpSwapFillRecord(
        signature=str(signatures[0]),
        slot=int(transaction.get("slot") or 0),
        block_time=None if block_time is None else datetime.fromtimestamp(int(block_time), UTC),
        network_fee_lamports=int(meta.get("fee") or 0),
        event=events[0] if events else None,
        payer_delta_lamports=delta,
        event_error=event_error,
        wsol_ata_pre_lamports=_wsol_ata_pre_lamports(transaction, meta),
        cashback_init_lamports=_cashback_init_lamports(transaction, meta),
    )
    return [record]


@dataclass(frozen=True, slots=True)
class BuiltPumpSwapSell:
    intent: PumpSwapSellIntent
    message: bytes
    blockhash: str
    last_valid_block_height: int
    caps: ExecutionCaps
    quote: SellQuote
    creates_wsol_ata: bool

    def verify(self, raw: bytes) -> object:
        return verify_pumpswap_sell_message(
            raw,
            self.intent,
            compute_unit_limit_cap=self.caps.max_compute_unit_limit,
            compute_unit_price_cap_micro_lamports=self.caps.max_compute_unit_price_micro_lamports,
            expected_blockhash=self.blockhash,
        )

    def intent_json(self) -> dict[str, Any]:
        q = self.quote
        return {
            "venue": "pumpswap",
            "side": "sell",
            "pool": self.intent.pool_address,
            "base_amount_in": self.intent.base_amount_in,
            "min_quote_amount_out": self.intent.min_quote_amount_out,
            "blockhash": self.blockhash,
            "last_valid_block_height": self.last_valid_block_height,
            "compute_unit_limit": self.caps.max_compute_unit_limit,
            "compute_unit_price_micro_lamports": self.caps.max_compute_unit_price_micro_lamports,
            "creates_wsol_ata": self.creates_wsol_ata,
            "price_impact_bps": q.price_impact_bps,
            "max_slippage_bps": q.max_slippage_bps,
            "net_quote_amount": q.net_quote_amount,
            "buyback_fee_recipient": self.intent.buyback_fee_recipient,
        }


def build_pumpswap_sell(
    read: PoolRead,
    config: GlobalConfig,
    *,
    user: str,
    base_token_program: str,
    token_amount: int,
    max_slippage_bps: int,
    blockhash: str,
    last_valid_block_height: int,
    compute_unit_limit: int,
    compute_unit_price_micro_lamports: int,
    creates_wsol_ata: bool,
    pick_recipient: Callable[[Sequence[str]], str] = _RNG.choice,
) -> BuiltPumpSwapSell:
    if not config.buyback_fee_recipients:  # T4.8f: the program refuses a sell without one
        raise ValueError("pumpswap_buyback_recipients_unavailable")
    if read.pool.quote_mint != WSOL_MINT:  # the unwrap, fee ATAs and quote maths assume WSOL
        raise ValueError("pumpswap_quote_not_wsol")
    quote = quote_pool_sell(
        pool_reserves_of(read), token_amount, config, max_slippage_bps=max_slippage_bps
    )
    intent = PumpSwapSellIntent(
        pool_address=read.address,
        pool=read.pool,
        user=user,
        base_token_program=base_token_program,
        base_amount_in=token_amount,
        min_quote_amount_out=quote.min_quote_amount_out,
        protocol_fee_recipient=config.protocol_fee_recipients[0],
        buyback_fee_recipient=pick_recipient(config.buyback_fee_recipients),  # T4.8f F5
    )
    message = build_sell_message(
        intent,
        payer=user,
        recent_blockhash=blockhash,
        compute_unit_limit=compute_unit_limit,
        compute_unit_price_micro_lamports=compute_unit_price_micro_lamports,
        create_wsol_ata=creates_wsol_ata,
    )
    caps = ExecutionCaps(compute_unit_limit, compute_unit_price_micro_lamports)
    return BuiltPumpSwapSell(
        intent,
        serialize_message(message),
        blockhash,
        last_valid_block_height,
        caps,
        quote,
        creates_wsol_ata,
    )
