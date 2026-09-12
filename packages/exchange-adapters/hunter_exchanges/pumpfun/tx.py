"""``buy`` / ``sell`` instruction builder for the pump.fun bonding curve — pure, no network.

Account order, discriminators and argument layout follow the official IDL (GitHub
``main`` and the program's on-chain IDL account, both re-read on 2026-09-12: ``buy``
16 accounts, ``sell`` 14). What the IDL does *not* say comes from confirmed mainnet
transactions (``docs/PUMPFUN-ONCHAIN.md`` §6b/§6c):

1. **Remaining accounts** (T4.8b, four real trades pre- and post-upgrade): ``buy`` and
   ``sell`` end with the PDA ``["bonding-curve-v2", mint]`` (read-only, **derived per
   mint, never a constant** — T4.8's "undocumented ``4CLQ…``" was this PDA of its
   fixture coin; the program deployed 2026-09-12 15:24 UTC validates the slot, 6074)
   and one of the 8 ``Global.buyback_fee_recipients`` (writable). A **cashback coin**'s
   ``sell`` also passes ``user_volume_accumulator`` (writable) before the pair (6072
   otherwise); ``buy`` declares it in the IDL.
2. ``track_volume: OptionBool`` is *absent* in every real trade (24-byte data); it is
   only appended when the caller passes an explicit ``True``/``False``.

Everything that varies by coin is an **input**: the token program (the mint's owner),
the creator and the cashback/Mayhem flags (``BondingCurve``), the fee and buyback
recipients (``Global``; a Mayhem coin pays a *reserved* recipient). Compute-unit limit
and price are explicit parameters of :func:`build_trade_message`; the legacy SOL-only
pair is kept on purpose (the site moved to ``buy_exact_quote_in_v2``, §6c).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.global_state import GlobalAccount
from hunter_exchanges.pumpfun.solana_codec import (
    ASSOCIATED_TOKEN_PROGRAM_ID,
    SYSTEM_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    AccountMeta,
    Instruction,
    Message,
    associated_token_address,
    compile_message,
    find_program_address,
    pubkey_bytes,
    set_compute_unit_limit,
    set_compute_unit_price,
    u64_le,
)

__all__ = [
    "BUY_ACCOUNT_NAMES",
    "BUY_DISCRIMINATOR",
    "PUMP_FEE_PROGRAM_ID",
    "SELL_ACCOUNT_NAMES",
    "SELL_CASHBACK_ACCOUNT_NAMES",
    "SELL_DISCRIMINATOR",
    "DecodedTrade",
    "PumpPdas",
    "TradeIntent",
    "bonding_curve_address",
    "bonding_curve_v2_address",
    "build_buy_instruction",
    "build_sell_instruction",
    "build_trade_message",
    "create_ata_idempotent",
    "creator_vault_address",
    "decode_trade_instruction",
    "jito_tip_transfer",
    "pump_pdas",
    "trade_account_names",
    "user_volume_accumulator_address",
]

PUMP_FEE_PROGRAM_ID = "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"
BUY_DISCRIMINATOR = bytes.fromhex("66063d1201daebea")
SELL_DISCRIMINATOR = bytes.fromhex("33e685a4017f83ad")

_REMAINING_ACCOUNT_NAMES = ("bonding_curve_v2", "buyback_fee_recipient")
_DECLARED_BUY = (
    "global fee_recipient mint bonding_curve associated_bonding_curve associated_user user "
    "system_program token_program creator_vault event_authority program "
    "global_volume_accumulator user_volume_accumulator fee_config fee_program"
)
_DECLARED_SELL = (
    "global fee_recipient mint bonding_curve associated_bonding_curve associated_user user "
    "system_program creator_vault token_program event_authority program fee_config fee_program"
)
BUY_ACCOUNT_NAMES = (*_DECLARED_BUY.split(), *_REMAINING_ACCOUNT_NAMES)
"""IDL order (16 / 14) + the remaining accounts — the verifier names slots with these."""
SELL_ACCOUNT_NAMES = (*_DECLARED_SELL.split(), *_REMAINING_ACCOUNT_NAMES)
SELL_CASHBACK_ACCOUNT_NAMES = SELL_ACCOUNT_NAMES[:14] + (
    "user_volume_accumulator",
    *_REMAINING_ACCOUNT_NAMES,
)

_TOKEN_PROGRAMS = frozenset({TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID})


def trade_account_names(side: str, *, cashback: bool = False) -> tuple[str, ...]:
    sell = SELL_CASHBACK_ACCOUNT_NAMES if cashback else SELL_ACCOUNT_NAMES
    return BUY_ACCOUNT_NAMES if side == "buy" else sell


@dataclass(frozen=True, slots=True)
class PumpPdas:
    global_account: str
    event_authority: str
    fee_config: str
    global_volume_accumulator: str


def _pda(seeds: Sequence[bytes], program: str = PUMP_PROGRAM_ID) -> str:
    return find_program_address(seeds, program)[0]


@lru_cache(maxsize=1)
def pump_pdas() -> PumpPdas:
    """The mint-independent PDAs, derived once (``find_program_address`` is pure)."""
    return PumpPdas(
        global_account=_pda([b"global"]),
        event_authority=_pda([b"__event_authority"]),
        fee_config=_pda([b"fee_config", pubkey_bytes(PUMP_PROGRAM_ID)], PUMP_FEE_PROGRAM_ID),
        global_volume_accumulator=_pda([b"global_volume_accumulator"]),
    )


def bonding_curve_address(mint: str) -> str:
    return _pda([b"bonding-curve", pubkey_bytes(mint)])


def bonding_curve_v2_address(mint: str) -> str:
    """The remaining account the 2026-09-12 program validates (6074) — derived, never typed."""
    return _pda([b"bonding-curve-v2", pubkey_bytes(mint)])


def creator_vault_address(creator: str) -> str:
    return _pda([b"creator-vault", pubkey_bytes(creator)])


def user_volume_accumulator_address(user: str) -> str:
    return _pda([b"user_volume_accumulator", pubkey_bytes(user)])


@dataclass(frozen=True, slots=True)
class TradeIntent:
    """What a buy or sell is built from; ``sol_limit`` is ``max_sol_cost`` (buy) or
    ``min_sol_output`` (sell) — lamports from ``quote.py``'s explicit slippage."""

    side: Literal["buy", "sell"]
    mint: str
    user: str
    creator: str
    token_program: str
    token_amount: int
    sol_limit: int
    fee_recipient: str
    buyback_fee_recipient: str
    is_mayhem_mode: bool
    track_volume: bool | None = None
    is_cashback_coin: bool = False

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        if self.token_program not in _TOKEN_PROGRAMS:
            raise ValueError("token_program must be the SPL Token or Token-2022 program")
        if self.token_amount <= 0:
            raise ValueError("token_amount must be positive")
        if self.sol_limit < 0:
            raise ValueError("sol_limit must be >= 0")
        for name in ("mint", "user", "creator", "fee_recipient", "buyback_fee_recipient"):
            pubkey_bytes(getattr(self, name))


def _validate_recipients(intent: TradeIntent, global_account: GlobalAccount) -> None:
    allowed = global_account.fee_recipients_for(is_mayhem_mode=intent.is_mayhem_mode)
    if intent.fee_recipient not in allowed:
        kind = "reserved (Mayhem)" if intent.is_mayhem_mode else "normal"
        raise ValueError(f"fee_recipient is not one of Global's {kind} fee recipients")
    if intent.buyback_fee_recipient not in global_account.buyback_fee_recipients:
        raise ValueError("buyback_fee_recipient is not one of Global's buyback fee recipients")


def _data(discriminator: bytes, intent: TradeIntent) -> bytes:
    data = discriminator + u64_le(intent.token_amount) + u64_le(intent.sol_limit)
    if intent.track_volume is not None:
        data += b"\x01" if intent.track_volume else b"\x00"
    return data


def _w(pubkey: str) -> AccountMeta:
    return AccountMeta(pubkey, False, True)


def _r(pubkey: str) -> AccountMeta:
    return AccountMeta(pubkey, False, False)


def _remaining_accounts(intent: TradeIntent) -> tuple[AccountMeta, ...]:
    """The derived PDA + the buyback recipient; a cashback coin's ``sell`` leads with the accumulator."""
    pair = (_r(bonding_curve_v2_address(intent.mint)), _w(intent.buyback_fee_recipient))
    if intent.side == "sell" and intent.is_cashback_coin:
        return (_w(user_volume_accumulator_address(intent.user)), *pair)
    return pair


def build_buy_instruction(intent: TradeIntent, global_account: GlobalAccount) -> Instruction:
    """``buy(amount, max_sol_cost[, track_volume])`` — IDL order (16) + the pair (18)."""
    if intent.side != "buy":
        raise ValueError("intent.side must be 'buy'")
    _validate_recipients(intent, global_account)
    pdas = pump_pdas()
    curve = bonding_curve_address(intent.mint)
    accounts = (
        _r(pdas.global_account),
        _w(intent.fee_recipient),
        _r(intent.mint),
        _w(curve),
        _w(associated_token_address(curve, intent.mint, token_program=intent.token_program)),
        _w(associated_token_address(intent.user, intent.mint, token_program=intent.token_program)),
        AccountMeta(intent.user, True, True),
        _r(SYSTEM_PROGRAM_ID),
        _r(intent.token_program),
        _w(creator_vault_address(intent.creator)),
        _r(pdas.event_authority),
        _r(PUMP_PROGRAM_ID),
        _r(pdas.global_volume_accumulator),
        _w(user_volume_accumulator_address(intent.user)),
        _r(pdas.fee_config),
        _r(PUMP_FEE_PROGRAM_ID),
        *_remaining_accounts(intent),
    )
    return Instruction(PUMP_PROGRAM_ID, accounts, _data(BUY_DISCRIMINATOR, intent))


def build_sell_instruction(intent: TradeIntent, global_account: GlobalAccount) -> Instruction:
    """``sell(amount, min_sol_output)`` — IDL order (14) + the pair: 16, or 17 on a cashback coin."""
    if intent.side != "sell":
        raise ValueError("intent.side must be 'sell'")
    _validate_recipients(intent, global_account)
    pdas = pump_pdas()
    curve = bonding_curve_address(intent.mint)
    accounts = (
        _r(pdas.global_account),
        _w(intent.fee_recipient),
        _r(intent.mint),
        _w(curve),
        _w(associated_token_address(curve, intent.mint, token_program=intent.token_program)),
        _w(associated_token_address(intent.user, intent.mint, token_program=intent.token_program)),
        AccountMeta(intent.user, True, True),
        _r(SYSTEM_PROGRAM_ID),
        _w(creator_vault_address(intent.creator)),
        _r(intent.token_program),
        _r(pdas.event_authority),
        _r(PUMP_PROGRAM_ID),
        _r(pdas.fee_config),
        _r(PUMP_FEE_PROGRAM_ID),
        *_remaining_accounts(intent),
    )
    return Instruction(PUMP_PROGRAM_ID, accounts, _data(SELL_DISCRIMINATOR, intent))


def create_ata_idempotent(*, payer: str, owner: str, mint: str, token_program: str) -> Instruction:
    """Associated-token ``CreateIdempotent`` (instruction 1): the buyer's token account
    is created in the same transaction when missing, as the site does (``swap_build_probe4``)."""
    return Instruction(
        ASSOCIATED_TOKEN_PROGRAM_ID,
        (
            AccountMeta(payer, True, True),
            _w(associated_token_address(owner, mint, token_program=token_program)),
            _r(owner),
            _r(mint),
            _r(SYSTEM_PROGRAM_ID),
            _r(token_program),
        ),
        b"\x01",
    )


def jito_tip_transfer(*, payer: str, tip_account: str, lamports: int) -> Instruction:
    """System ``Transfer`` (index 2) of the bundle tip — to the named account, within the cap."""
    if lamports <= 0:
        raise ValueError("tip must be positive")
    return Instruction(
        SYSTEM_PROGRAM_ID,
        (AccountMeta(payer, True, True), _w(tip_account)),
        b"\x02\x00\x00\x00" + u64_le(lamports),
    )


def build_trade_message(
    trade: Instruction,
    *,
    payer: str,
    recent_blockhash: str,
    compute_unit_limit: int,
    compute_unit_price_micro_lamports: int,
    create_user_ata: Instruction | None = None,
    jito_tip: Instruction | None = None,
) -> Message:
    """[cu limit, cu price, (create ATA), trade, (tip)] as a legacy message — the canonical
    order the verifier rebuilds byte for byte. Both compute-budget values are mandatory:
    a default would be a silent priority-fee policy (``RISK_ENGINE_MEME.md`` §3.1)."""
    instructions = [
        set_compute_unit_limit(compute_unit_limit),
        set_compute_unit_price(compute_unit_price_micro_lamports),
    ]
    if create_user_ata is not None:
        instructions.append(create_user_ata)
    instructions.append(trade)
    if jito_tip is not None:
        instructions.append(jito_tip)
    return compile_message(payer, instructions, recent_blockhash)


@dataclass(frozen=True, slots=True)
class DecodedTrade:
    side: Literal["buy", "sell"]
    token_amount: int
    sol_limit: int
    track_volume: bool | None
    accounts: tuple[AccountMeta, ...]


def decode_trade_instruction(instruction: Instruction) -> DecodedTrade:
    """Inverse of the builders' data layout, for the verifier and for tests."""
    if instruction.program_id != PUMP_PROGRAM_ID:
        raise ValueError("not a pump program instruction")
    data = instruction.data
    if len(data) not in (24, 25):
        raise ValueError(f"trade data must be 24 or 25 bytes, got {len(data)}")
    if data[:8] == BUY_DISCRIMINATOR:
        side: Literal["buy", "sell"] = "buy"
    elif data[:8] == SELL_DISCRIMINATOR:
        side = "sell"
    else:
        raise ValueError("unknown pump instruction discriminator")
    track_volume: bool | None = None
    if len(data) == 25:
        if data[24] not in (0, 1):
            raise ValueError("track_volume must be 0 or 1")
        track_volume = bool(data[24])
    return DecodedTrade(
        side=side,
        token_amount=int.from_bytes(data[8:16], "little"),
        sol_limit=int.from_bytes(data[16:24], "little"),
        track_volume=track_volume,
        accounts=instruction.accounts,
    )
