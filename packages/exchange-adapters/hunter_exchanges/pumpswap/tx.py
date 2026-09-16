"""``sell`` instruction builder for a PumpSwap pool — pure, no network (T4.29a).

Account order, discriminator and argument layout come straight from the
program's own on-chain IDL (``tests/fixtures/pumpswap/t429a_idl_pump_amm_onchain.json``,
sha256 in ``decode.py``'s module docstring): ``sell`` — 21 accounts, args
``base_amount_in: u64, min_quote_amount_out: u64``. The discriminator
(``33e685a4017f83ad``) is byte-identical to the bonding curve's ``sell`` —
Anchor discriminators are ``sha256("global:<name>")[:8]``, so any two programs
that both name an instruction ``sell`` collide; only the *program id* in the
instruction tells them apart (already documented for ``buy`` in
``docs/PUMPFUN-ONCHAIN.md`` §2.3, confirmed again here for ``sell``).

**PumpSwap's quote side is wrapped SOL, never native SOL** (``decode.py``):
selling leaves proceeds in the user's WSOL associated token account, so this
module also builds the **unwrap** step — an idempotent ``CreateIdempotent``
of that ATA before the trade (if the wallet has never held WSOL) and an SPL
Token ``CloseAccount`` after it, which drains the ATA's lamports (rent +
whatever WSOL it now holds) to the wallet and closes it, exactly as the
official ``@solana/spl-token`` "sync native / close" unwrap pattern does.
Nothing here buys on PumpSwap — there is no ``build_buy_instruction`` in this
package (``docs/RISK_ENGINE_MEME.md`` §1: PumpSwap is exit-only).
"""

from __future__ import annotations

from dataclasses import dataclass

from hunter_exchanges.pumpfun.solana_codec import (
    ASSOCIATED_TOKEN_PROGRAM_ID,
    SYSTEM_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    AccountMeta,
    Instruction,
    Message,
    associated_token_address,
    compile_message,
    set_compute_unit_limit,
    set_compute_unit_price,
    u64_le,
)
from hunter_exchanges.pumpswap.decode import (
    GLOBAL_CONFIG_ADDRESS,
    PUMPSWAP_PROGRAM_ID,
    WSOL_MINT,
    Pool,
)
from hunter_exchanges.pumpswap.pdas import (
    PUMP_FEE_PROGRAM_ID,
    coin_creator_vault,
    event_authority,
    fee_config_address,
)

__all__ = [
    "SELL_ACCOUNT_NAMES",
    "SELL_DISCRIMINATOR",
    "PumpSwapSellIntent",
    "build_close_wsol_instruction",
    "build_create_wsol_ata_instruction",
    "build_pumpswap_sell_instruction",
    "build_sell_message",
]

SELL_DISCRIMINATOR = bytes.fromhex("33e685a4017f83ad")

SELL_ACCOUNT_NAMES = (
    "pool user global_config base_mint quote_mint user_base_token_account "
    "user_quote_token_account pool_base_token_account pool_quote_token_account "
    "protocol_fee_recipient protocol_fee_recipient_token_account base_token_program "
    "quote_token_program system_program associated_token_program event_authority program "
    "coin_creator_vault_ata coin_creator_vault_authority fee_config fee_program"
).split()
assert len(SELL_ACCOUNT_NAMES) == 21


@dataclass(frozen=True, slots=True)
class PumpSwapSellIntent:
    """What a PumpSwap sell is built from — mirrors ``pumpfun.tx.TradeIntent``.

    ``protocol_fee_recipient`` is the caller's choice among
    ``GlobalConfig.protocol_fee_recipients`` — validated by the caller
    (``build_pumpswap_sell.py`` in the executor), not here: this module is
    pure and does not fetch ``GlobalConfig``.
    """

    pool_address: str
    pool: Pool
    user: str
    base_token_program: str
    base_amount_in: int
    min_quote_amount_out: int
    protocol_fee_recipient: str

    def __post_init__(self) -> None:
        if self.base_amount_in <= 0:
            raise ValueError("base_amount_in must be positive")
        if self.min_quote_amount_out < 0:
            raise ValueError("min_quote_amount_out must be >= 0")


def _w(pubkey: str) -> AccountMeta:
    return AccountMeta(pubkey, False, True)


def _r(pubkey: str) -> AccountMeta:
    return AccountMeta(pubkey, False, False)


def build_pumpswap_sell_instruction(intent: PumpSwapSellIntent) -> Instruction:
    """``sell(base_amount_in, min_quote_amount_out)`` — IDL order, 21 accounts."""
    pool, user = intent.pool, intent.user
    vault_authority, vault_ata = coin_creator_vault(pool.coin_creator)
    protocol_fee_recipient_ata = associated_token_address(
        intent.protocol_fee_recipient, WSOL_MINT, token_program=TOKEN_PROGRAM_ID
    )
    accounts = (
        _w(intent.pool_address),
        AccountMeta(user, True, True),
        _r(GLOBAL_CONFIG_ADDRESS),
        _r(pool.base_mint),
        _r(pool.quote_mint),
        _w(associated_token_address(user, pool.base_mint, token_program=intent.base_token_program)),
        _w(associated_token_address(user, WSOL_MINT, token_program=TOKEN_PROGRAM_ID)),
        _w(pool.pool_base_token_account),
        _w(pool.pool_quote_token_account),
        _r(intent.protocol_fee_recipient),
        _w(protocol_fee_recipient_ata),
        _r(intent.base_token_program),
        _r(TOKEN_PROGRAM_ID),
        _r(SYSTEM_PROGRAM_ID),
        _r(ASSOCIATED_TOKEN_PROGRAM_ID),
        _r(event_authority()),
        _r(PUMPSWAP_PROGRAM_ID),
        _w(vault_ata),
        _r(vault_authority),
        _r(fee_config_address()),
        _r(PUMP_FEE_PROGRAM_ID),
    )
    data = SELL_DISCRIMINATOR + u64_le(intent.base_amount_in) + u64_le(intent.min_quote_amount_out)
    return Instruction(PUMPSWAP_PROGRAM_ID, accounts, data)


def build_create_wsol_ata_instruction(*, payer: str, owner: str) -> Instruction:
    """Associated-token ``CreateIdempotent`` (index 1) of the wallet's WSOL
    account — created once, before the first PumpSwap sell needs it."""
    return Instruction(
        ASSOCIATED_TOKEN_PROGRAM_ID,
        (
            AccountMeta(payer, True, True),
            _w(associated_token_address(owner, WSOL_MINT, token_program=TOKEN_PROGRAM_ID)),
            _r(owner),
            _r(WSOL_MINT),
            _r(SYSTEM_PROGRAM_ID),
            _r(TOKEN_PROGRAM_ID),
        ),
        b"\x01",
    )


def build_close_wsol_instruction(*, owner: str) -> Instruction:
    """SPL Token ``CloseAccount`` (index 9) on the wallet's WSOL ATA — the
    unwrap: drains it (rent + this sell's proceeds) to ``owner`` and closes
    it, ``owner`` signing as both the account's owner and the destination."""
    wsol_ata = associated_token_address(owner, WSOL_MINT, token_program=TOKEN_PROGRAM_ID)
    return Instruction(
        TOKEN_PROGRAM_ID,
        (_w(wsol_ata), _w(owner), AccountMeta(owner, True, False)),
        b"\x09",
    )


def build_sell_message(
    intent: PumpSwapSellIntent,
    *,
    payer: str,
    recent_blockhash: str,
    compute_unit_limit: int,
    compute_unit_price_micro_lamports: int,
    create_wsol_ata: bool,
) -> Message:
    """``[cu limit, cu price, (create WSOL ATA), sell, close WSOL ATA]`` — the
    canonical order the verifier rebuilds byte for byte (mirrors
    ``hunter_exchanges.pumpfun.tx.build_trade_message``). The unwrap always
    runs: a sell with nothing to unwrap simply closes an empty-of-proceeds,
    just-created ATA back to rent."""
    instructions = [
        set_compute_unit_limit(compute_unit_limit),
        set_compute_unit_price(compute_unit_price_micro_lamports),
    ]
    if create_wsol_ata:
        instructions.append(build_create_wsol_ata_instruction(payer=payer, owner=intent.user))
    instructions.append(build_pumpswap_sell_instruction(intent))
    instructions.append(build_close_wsol_instruction(owner=intent.user))
    return compile_message(payer, instructions, recent_blockhash)
