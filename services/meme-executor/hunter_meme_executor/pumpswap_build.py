"""From an approved PumpSwap sell to the bytes the submitter signs, and from a
landed transaction to the fill (T4.29a). Mirrors ``build.py``'s ``BuiltTrade``/
``FillRecord`` for the curve, one venue over: **sell only**, never a buy
(``docs/RISK_ENGINE_MEME.md`` §1 — PumpSwap is exit-only for a migrated
position).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from hunter_exchanges.pumpfun.solana_codec import serialize_message
from hunter_exchanges.pumpswap.decode import GlobalConfig
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

    @property
    def sell_net_lamports(self) -> int:
        if self.payer_delta_lamports is not None:
            return self.payer_delta_lamports
        if self.event is not None:
            return self.event.net_proceeds - self.network_fee_lamports
        return 0

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
            "network_fee_lamports": self.network_fee_lamports,
            "payer_delta_lamports": self.payer_delta_lamports,
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


def decode_pumpswap_fills(transaction: dict[str, Any]) -> list[PumpSwapFillRecord]:
    """``decode_fill`` for the submitter, PumpSwap edition. A landed
    transaction with no decodable ``SellEvent`` still yields one record keyed
    on the payer's balance delta — the WSOL unwrap makes that delta the
    honest net proceeds even when the event itself cannot be parsed."""
    meta = cast(dict[str, Any], transaction.get("meta") or {})
    if meta.get("err") is not None:
        return []
    tx = cast(dict[str, Any], transaction.get("transaction") or {})
    signatures = cast(list[Any], tx.get("signatures") or [""])
    block_time = transaction.get("blockTime")
    events = sell_events_from_transaction(transaction)
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
) -> BuiltPumpSwapSell:
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
