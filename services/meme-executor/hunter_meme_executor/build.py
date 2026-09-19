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
from decimal import Decimal
from typing import Any

from hunter_exchanges.pumpfun.decode import NATIVE_SOL_QUOTE_MINT, BondingCurveAccount
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
from hunter_exchanges.pumpfun.tx import (
    TradeIntent,
    build_buy_instruction,
    build_close_ata_instruction,
    build_sell_instruction,
    build_trade_message,
    create_ata_idempotent,
)
from hunter_exchanges.pumpfun.verify import ExecutionCaps, verify_trade_message
from hunter_meme_executor.chain import CurveRead
from hunter_meme_executor.fills import FillRecord, decode_fills

__all__ = [
    "BuiltTrade",
    "FillRecord",
    "build_buy",
    "build_sell",
    "decode_fills",
    "fee_bps",
    "reserves_of",
    "reserves_of_account",
]

LAMPORTS_PER_SOL = 1_000_000_000


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
    closes_ata: bool = False
    """T4.46 — a full sell that appends ``CloseAccount`` for the mint's ATA
    (never a buy, never a partial sell: the on-chain balance would refuse it)."""

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
            "closes_ata": self.closes_ata,
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
    return reserves_of_account(read.account)


def reserves_of_account(a: BondingCurveAccount) -> CurveReserves:
    """T4.63: the same reserves off a decoded account — an ``accountNotification``
    (``event_exits.py``) is the same bytes ``ChainReader.curve`` reads by HTTP."""
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
    wallet_token_balance: int | None = None,
    close_ata_on_full_sell: bool = True,
) -> BuiltTrade:
    """A full sell (``token_amount == wallet_token_balance``, both positive) also
    closes the mint's ATA when ``close_ata_on_full_sell`` (T4.46, env
    ``MEME_CLOSE_ATA_ON_FULL_SELL``, default on): the rent (R43: ~0.0015 SOL a
    coin) comes back to the wallet instead of staying parked. A partial sell —
    the on-chain balance would refuse ``CloseAccount`` on a non-empty account —
    never appends it."""
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
    closes_ata = (
        close_ata_on_full_sell
        and wallet_token_balance is not None
        and token_amount > 0
        and token_amount == wallet_token_balance
    )
    message = build_trade_message(
        build_sell_instruction(intent, global_account),
        payer=user,
        recent_blockhash=blockhash,
        compute_unit_limit=compute_unit_limit,
        compute_unit_price_micro_lamports=compute_unit_price_micro_lamports,
        close_ata=(
            build_close_ata_instruction(
                owner=user, mint=read.mint, token_program=read.token_program
            )
            if closes_ata
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
        False,
        closes_ata,
    )
