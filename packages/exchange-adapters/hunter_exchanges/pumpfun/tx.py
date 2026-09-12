"""``buy`` / ``sell`` instruction builder for the pump.fun bonding curve — pure, no network.

Account order, discriminators and argument layout follow the official IDL
(``pump-fun/pump-public-docs`` ``idl/pump.json``, commit ``9c82f61`` — re-read from
GitHub ``main`` **and** from the program's on-chain IDL account on 2026-09-12; all
three agree: ``buy`` 16 accounts, ``sell`` 14). Two things the IDL does *not* say
were taken from confirmed mainnet transactions (``docs/PUMPFUN-ONCHAIN.md`` §6b):

1. Both the site's own router (``rpc_tx_buy_raw.json``, inner CPI) and an
   independent bot (``rpc_tx_probe_raw.json``, a direct ``sell``) append the same
   **remaining accounts**: for ``sell`` — ``user_volume_accumulator`` (writable,
   where cashback accrues), :data:`UNDOCUMENTED_REMAINING_ACCOUNT` (read-only,
   does not exist on chain, unnamed in every IDL we could read) and one of the 8
   ``buyback_fee_recipients``; for ``buy`` the IDL already carries the
   accumulators, so only the last two are appended. The parity tests assert our
   instruction equals those two real ones byte for byte.
2. ``track_volume: OptionBool`` is *absent* in both (24-byte data); it is only
   appended when the caller passes an explicit ``True``/``False``.

Everything that varies by coin is an **input**: the token program (Token-2022 on
the coin above — read it from the mint account's owner), the creator (from the
``BondingCurve`` account), the fee recipient and the buyback recipient (from the
``Global`` account, ``global_state.py`` — a Mayhem coin pays one of the *reserved*
recipients, selected by ``BondingCurve.is_mayhem_mode``). Compute-unit limit and
price are explicit parameters of :func:`build_trade_message` with no default.
"""

from __future__ import annotations

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
    "BUY_DISCRIMINATOR",
    "PUMP_FEE_PROGRAM_ID",
    "SELL_DISCRIMINATOR",
    "UNDOCUMENTED_REMAINING_ACCOUNT",
    "DecodedTrade",
    "PumpPdas",
    "TradeIntent",
    "bonding_curve_address",
    "build_buy_instruction",
    "build_sell_instruction",
    "build_trade_message",
    "create_ata_idempotent",
    "creator_vault_address",
    "decode_trade_instruction",
    "jito_tip_transfer",
    "pump_pdas",
    "user_volume_accumulator_address",
]

PUMP_FEE_PROGRAM_ID = "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"
BUY_DISCRIMINATOR = bytes.fromhex("66063d1201daebea")
SELL_DISCRIMINATOR = bytes.fromhex("33e685a4017f83ad")

UNDOCUMENTED_REMAINING_ACCOUNT = "4CLQeN5wrddJ9adY3GJGSTyu1AEKD4Ta14RffSy5aHud"
"""Read-only remaining account both the site's router and an independent bot pass
right before the buyback recipient. ``getAccountInfo`` returns null for it (captured
in ``rpc_account_4CLQ_raw.json``); it is not a PDA we could derive under any of the
four pump programs nor an ATA of any account involved; the GitHub-``main`` and the
on-chain IDL do not mention it. Kept verbatim so our instruction is byte-identical
to the ones the program accepted; its necessity is probed by the mainnet
simulation in ``test_pumpfun_simulation_proof.py``."""

_TOKEN_PROGRAMS = frozenset({TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID})


@dataclass(frozen=True, slots=True)
class PumpPdas:
    global_account: str
    event_authority: str
    fee_config: str
    global_volume_accumulator: str


@lru_cache(maxsize=1)
def pump_pdas() -> PumpPdas:
    """The mint-independent PDAs, derived once (``find_program_address`` is pure)."""
    return PumpPdas(
        global_account=find_program_address([b"global"], PUMP_PROGRAM_ID)[0],
        event_authority=find_program_address([b"__event_authority"], PUMP_PROGRAM_ID)[0],
        fee_config=find_program_address(
            [b"fee_config", pubkey_bytes(PUMP_PROGRAM_ID)], PUMP_FEE_PROGRAM_ID
        )[0],
        global_volume_accumulator=find_program_address(
            [b"global_volume_accumulator"], PUMP_PROGRAM_ID
        )[0],
    )


def bonding_curve_address(mint: str) -> str:
    return find_program_address([b"bonding-curve", pubkey_bytes(mint)], PUMP_PROGRAM_ID)[0]


def creator_vault_address(creator: str) -> str:
    return find_program_address([b"creator-vault", pubkey_bytes(creator)], PUMP_PROGRAM_ID)[0]


def user_volume_accumulator_address(user: str) -> str:
    return find_program_address([b"user_volume_accumulator", pubkey_bytes(user)], PUMP_PROGRAM_ID)[
        0
    ]


@dataclass(frozen=True, slots=True)
class TradeIntent:
    """Everything a buy or sell instruction is built from. ``sol_limit`` is
    ``max_sol_cost`` for a buy and ``min_sol_output`` for a sell — lamports, computed
    by ``quote.py`` from an explicit slippage, never a percentage here."""

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


def build_buy_instruction(intent: TradeIntent, global_account: GlobalAccount) -> Instruction:
    """``buy(amount, max_sol_cost[, track_volume])`` — IDL order, then the two
    remaining accounts the program accepts today."""
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
        _r(UNDOCUMENTED_REMAINING_ACCOUNT),
        _w(intent.buyback_fee_recipient),
    )
    return Instruction(PUMP_PROGRAM_ID, accounts, _data(BUY_DISCRIMINATOR, intent))


def build_sell_instruction(intent: TradeIntent, global_account: GlobalAccount) -> Instruction:
    """``sell(amount, min_sol_output)`` — IDL order (note ``creator_vault`` *before*
    ``token_program`` here, unlike ``buy``), then the three remaining accounts."""
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
        _w(user_volume_accumulator_address(intent.user)),
        _r(UNDOCUMENTED_REMAINING_ACCOUNT),
        _w(intent.buyback_fee_recipient),
    )
    return Instruction(PUMP_PROGRAM_ID, accounts, _data(SELL_DISCRIMINATOR, intent))


def create_ata_idempotent(*, payer: str, owner: str, mint: str, token_program: str) -> Instruction:
    """Associated-token ``CreateIdempotent`` (instruction 1): the buyer's token account
    is created in the same transaction when it does not exist yet, exactly as the
    site does (``swap_build_probe4_raw.txt``)."""
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
    """System ``Transfer`` (index 2) of the bundle tip — only ever to the named tip
    account, only ever within ``max_jito_tip_sol`` (verified in ``verify.py``)."""
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
    """[cu limit, cu price, (create ATA), trade, (tip)] compiled into a legacy message
    — the **canonical order** the verifier rebuilds and compares byte for byte.
    Both compute-budget values are mandatory: a default here would be a silent
    priority-fee policy (``docs/RISK_ENGINE_MEME.md`` §3.1 caps them by name)."""
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
