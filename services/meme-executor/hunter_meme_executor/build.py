"""From an approved decision to the bytes the submitter signs — and from a landed
transaction to the fill the ledger records.

Composes T4.8's pure pieces (``quote``, ``tx``, ``verify``, ``trade_event``) with the
executor's config. Policy here: *which* fee recipients a coin pays (``Global``'s normal
or reserved list, by ``is_mayhem_mode``; admission refuses Mayhem coins anyway) and a
named refusal of any curve whose quote is not SOL (T4.8b: USDC-quoted coins exist and
the legacy ``buy``/``sell`` answer them with ``UnsupportedQuoteMint`` 6063).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from hunter_exchanges.pumpfun.decode import NATIVE_SOL_QUOTE_MINT, PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.global_state import GlobalAccount
from hunter_exchanges.pumpfun.quote import (
    BONDING_CURVE_FEE_TIER_2026_05_20,
    BuyQuote,
    CurveReserves,
    FeeBps,
    SellQuote,
    quote_buy_for_budget,
    quote_sell,
)
from hunter_exchanges.pumpfun.solana_codec import serialize_message
from hunter_exchanges.pumpfun.trade_event import TradeEvent, trade_events_from_transaction
from hunter_exchanges.pumpfun.tx import (
    TradeIntent,
    build_buy_instruction,
    build_sell_instruction,
    build_trade_message,
    create_ata_idempotent,
)
from hunter_exchanges.pumpfun.verify import ExecutionCaps, verify_trade_message
from hunter_meme_executor.chain import CurveRead

__all__ = [
    "BuiltTrade",
    "FillRecord",
    "build_buy",
    "build_sell",
    "decode_fills",
    "fee_bps",
    "reserves_of",
]

LAMPORTS_PER_SOL = 1_000_000_000


@dataclass(frozen=True, slots=True)
class FillRecord:
    """The fill as the chain reported it (§9.6): the ``TradeEvent``, ``meta.fee`` and — the
    ledger's truth — the payer's real balance delta (``pre − post`` of index 0), which carries
    everything the wallet lost or gained: curve, every fee the program has, rent, tips."""

    event: TradeEvent
    signature: str
    slot: int
    block_time: datetime | None
    network_fee_lamports: int
    payer_delta_lamports: int | None = None
    """``post − pre`` of the payer (negative on a buy); ``None`` without balances."""

    @property
    def event_buy_total_lamports(self) -> int:
        """Curve + the event's fees + network fee — lamport-exact on the recorded fills."""
        return self.event.buy_total_cost + self.network_fee_lamports

    @property
    def event_sell_net_lamports(self) -> int:
        return self.event.sell_net_proceeds - self.network_fee_lamports

    @property
    def buy_total_lamports(self) -> int:
        """Everything the buy took from the wallet — the chain's delta when known."""
        if self.payer_delta_lamports is not None:
            return -self.payer_delta_lamports
        return self.event_buy_total_lamports

    @property
    def sell_net_lamports(self) -> int:
        if self.payer_delta_lamports is not None:
            return self.payer_delta_lamports
        return self.event_sell_net_lamports

    @property
    def unexplained_lamports(self) -> int | None:
        """Beyond the event's arithmetic and the network fee (a router's cut, ATA rent):
        ``0`` on a transaction this executor builds; ``None`` without balances (T4.8b)."""
        if self.payer_delta_lamports is None:
            return None
        if self.event.is_buy:
            return -self.payer_delta_lamports - self.event_buy_total_lamports
        return self.event_sell_net_lamports - self.payer_delta_lamports

    def as_json(self) -> dict[str, Any]:
        e = self.event
        return {
            "signature": self.signature,
            "slot": self.slot,
            "block_time": None if self.block_time is None else self.block_time.isoformat(),
            "mint": e.mint,
            "is_buy": e.is_buy,
            "sol_amount": e.sol_amount,
            "token_amount": e.token_amount,
            "fee": e.fee,
            "fee_basis_points": e.fee_basis_points,
            "creator_fee": e.creator_fee,
            "creator_fee_basis_points": e.creator_fee_basis_points,
            "cashback": e.cashback,
            "holder_rewards": e.holder_rewards,
            "holder_rewards_basis_points": e.holder_rewards_basis_points,
            "event_layout": e.layout,
            "network_fee_lamports": self.network_fee_lamports,
            "payer_delta_lamports": self.payer_delta_lamports,
            "unexplained_lamports": self.unexplained_lamports,
            "buy_total_lamports": self.buy_total_lamports if e.is_buy else None,
            "event_buy_total_lamports": self.event_buy_total_lamports if e.is_buy else None,
            "sell_net_lamports": self.sell_net_lamports if not e.is_buy else None,
            "event_sell_net_lamports": self.event_sell_net_lamports if not e.is_buy else None,
            "virtual_sol_reserves_after": e.virtual_sol_reserves,
            "virtual_token_reserves_after": e.virtual_token_reserves,
            "real_token_reserves_after": e.real_token_reserves,
            "timestamp": e.timestamp,
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


def decode_fills(transaction: dict[str, Any]) -> list[FillRecord]:
    """``decode_fill`` for the submitter: the ``TradeEvent``s of a ``getTransaction`` result."""
    events = trade_events_from_transaction(transaction, program_id=PUMP_PROGRAM_ID)
    if not events:
        return []
    meta = cast(dict[str, Any], transaction.get("meta") or {})
    tx = cast(dict[str, Any], transaction.get("transaction") or {})
    signatures = cast(list[Any], tx.get("signatures") or [""])
    block_time = transaction.get("blockTime")
    # One transaction, one payer delta: attributed to the first event (no bundles built here).
    delta = _payer_delta(meta)
    return [
        FillRecord(
            event=event,
            signature=str(signatures[0]),
            slot=int(transaction.get("slot") or 0),
            block_time=None if block_time is None else datetime.fromtimestamp(int(block_time), UTC),
            network_fee_lamports=int(meta.get("fee") or 0),
            payer_delta_lamports=delta if index == 0 else None,
        )
        for index, event in enumerate(events)
    ]


@dataclass(frozen=True, slots=True)
class BuiltTrade:
    intent: TradeIntent
    message: bytes
    blockhash: str
    last_valid_block_height: int
    caps: ExecutionCaps
    global_account: GlobalAccount
    quote: BuyQuote | SellQuote
    creates_ata: bool

    def verify(self, raw: bytes) -> object:
        """The §9.1 verifier bound to this intent — what the submitter is given."""
        return verify_trade_message(
            raw, self.intent, self.global_account, self.caps, expected_blockhash=self.blockhash
        )

    def intent_json(self) -> dict[str, Any]:
        q = self.quote
        base: dict[str, Any] = {
            "side": self.intent.side,
            "mint": self.intent.mint,
            "token_amount": self.intent.token_amount,
            "sol_limit": self.intent.sol_limit,
            "blockhash": self.blockhash,
            "last_valid_block_height": self.last_valid_block_height,
            "compute_unit_limit": self.caps.max_compute_unit_limit,
            "compute_unit_price_micro_lamports": self.caps.max_compute_unit_price_micro_lamports,
            "creates_ata": self.creates_ata,
            "price_impact_bps": q.price_impact_bps,
            "max_slippage_bps": q.max_slippage_bps,
        }
        if isinstance(q, BuyQuote):
            base["total_cost_lamports"] = q.total_cost
            base["max_sol_cost"] = q.max_sol_cost
        else:
            base["net_proceeds_lamports"] = q.net_proceeds
            base["min_sol_output"] = q.min_sol_output
        return base


def reserves_of(read: CurveRead) -> CurveReserves:
    a = read.account
    if a.quote_mint != NATIVE_SOL_QUOTE_MINT:
        raise ValueError(f"unsupported_quote:{a.quote_mint}")
    return CurveReserves(
        a.virtual_sol_reserves,
        a.virtual_token_reserves,
        a.real_sol_reserves,
        a.real_token_reserves,
        a.complete,
    )


def fee_bps(global_account: GlobalAccount) -> FeeBps:
    """Protocol bps from ``Global``; the creator share **floored at the bonding-curve tier**
    (30 bps): ``Global.creator_fee_basis_points`` reads 5 while ``GetFeesWithQuoteMint``
    charged 30 on every recorded fill (T4.8b) — under-estimating breaches the budget ceiling."""
    tier = BONDING_CURVE_FEE_TIER_2026_05_20
    return FeeBps(
        protocol=max(global_account.fee_basis_points, tier.protocol),
        creator=max(global_account.creator_fee_basis_points, tier.creator),
    )


def _intent(
    side: str,
    read: CurveRead,
    *,
    user: str,
    token_amount: int,
    sol_limit: int,
    global_account: GlobalAccount,
) -> TradeIntent:
    mayhem = read.account.is_mayhem_mode
    return TradeIntent(
        "buy" if side == "buy" else "sell",
        read.mint,
        user,
        read.account.creator,
        read.token_program,
        token_amount,
        sol_limit,
        global_account.reserved_fee_recipient if mayhem else global_account.fee_recipient,
        global_account.buyback_fee_recipients[0],
        mayhem,
        is_cashback_coin=read.account.is_cashback_coin,
    )


def build_buy(
    read: CurveRead,
    global_account: GlobalAccount,
    *,
    user: str,
    budget_sol: Decimal,
    max_slippage_bps: int,
    blockhash: str,
    last_valid_block_height: int,
    compute_unit_limit: int,
    compute_unit_price_micro_lamports: int,
    creates_ata: bool,
) -> BuiltTrade:
    """The largest buy whose total (curve + fees) fits ``budget_sol`` — a ceiling, never a target."""
    budget = int(budget_sol * LAMPORTS_PER_SOL)
    quote = quote_buy_for_budget(
        reserves_of(read), budget, fee_bps(global_account), max_slippage_bps=max_slippage_bps
    )
    intent = _intent(
        "buy",
        read,
        user=user,
        token_amount=quote.token_amount,
        sol_limit=quote.max_sol_cost,
        global_account=global_account,
    )
    message = build_trade_message(
        build_buy_instruction(intent, global_account),
        payer=user,
        recent_blockhash=blockhash,
        compute_unit_limit=compute_unit_limit,
        compute_unit_price_micro_lamports=compute_unit_price_micro_lamports,
        create_user_ata=(
            create_ata_idempotent(
                payer=user, owner=user, mint=read.mint, token_program=read.token_program
            )
            if creates_ata
            else None
        ),
    )
    caps = ExecutionCaps(compute_unit_limit, compute_unit_price_micro_lamports)
    return BuiltTrade(
        intent,
        serialize_message(message),
        blockhash,
        last_valid_block_height,
        caps,
        global_account,
        quote,
        creates_ata,
    )


def build_sell(
    read: CurveRead,
    global_account: GlobalAccount,
    *,
    user: str,
    token_amount: int,
    max_slippage_bps: int,
    blockhash: str,
    last_valid_block_height: int,
    compute_unit_limit: int,
    compute_unit_price_micro_lamports: int,
) -> BuiltTrade:
    quote = quote_sell(
        reserves_of(read), token_amount, fee_bps(global_account), max_slippage_bps=max_slippage_bps
    )
    intent = _intent(
        "sell",
        read,
        user=user,
        token_amount=token_amount,
        sol_limit=quote.min_sol_output,
        global_account=global_account,
    )
    message = build_trade_message(
        build_sell_instruction(intent, global_account),
        payer=user,
        recent_blockhash=blockhash,
        compute_unit_limit=compute_unit_limit,
        compute_unit_price_micro_lamports=compute_unit_price_micro_lamports,
    )
    caps = ExecutionCaps(compute_unit_limit, compute_unit_price_micro_lamports)
    return BuiltTrade(
        intent,
        serialize_message(message),
        blockhash,
        last_valid_block_height,
        caps,
        global_account,
        quote,
        False,
    )
