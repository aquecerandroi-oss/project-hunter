"""PDA derivations for the canonical PumpSwap pool of a migrated mint (T4.29a).

**``pool_authority`` and the canonical ``pool`` seeds are read from the Pump
program's own on-chain IDL** (``migrate``/``migrate_v2`` accounts,
``tests/fixtures/pumpfun/t48c_rpc_idl_account_raw.json`` — already captured by
T4.8c, re-used here read-only): ``pool_authority = PDA(["pool-authority",
mint], PUMP_PROGRAM_ID)``; ``pool = PDA(["pool", u16_le(0), pool_authority,
mint, WSOL_MINT], PUMPSWAP_PROGRAM_ID)`` — index ``0`` because ``migrate``'s
CPI into ``create_pool`` always passes the program's own PDA as ``creator``
(``docs/PUMPFUN-ONCHAIN.md`` §2.3), so every coin-migration pool is the
canonical, index-0 one.

**Verified against 3 real migrated mints, live, 2026-09-16**
(``tests/fixtures/pumpswap/t429a_rpc_pools_raw.json`` /
``t429a_frontend_complete_raw.json``): the derived address matched the
``pool_address`` the REST API reports for all three
(``9tiUg9bDHpEgE3rQU8kmdMJMvMfwM81ph6WuyTapump`` →
``2KJ15ekBMtR2FW2esGeJrptrYLx6V9v5KEeuD8imKEz6``;
``DHcQCSZ2U8QTjNWWwyuqfJbBTLCZyvtFkSeYhEYGpump`` →
``8EpQ5ihpebcsns3DdEDoiu1WXu4GJZY9o9kSjbXAgArE``;
``5RFwNs16ShCeSNQY9Kf5iR5esbEMsnYm7PbWGQAwpump`` →
``F5MkE4Yf73TkeSKLv3Mr3yrGJpFg3g7sspaCosVYyxaQ``, this last one also the
``pumpfun`` package's existing ``frontend_api_v3_coin_graduated_raw.json``
fixture). No RPC read is needed to *find* a migrated mint's pool — only to
confirm it exists (``pumpswap_pool_not_found`` when ``getAccountInfo`` on the
derived address comes back empty, T4.29a's named refusal).

``coin_creator_vault_authority``/``_ata`` and ``fee_config`` are also derived
here, from the ``sell`` instruction's own PDA seeds in the same on-chain IDL
(``tests/fixtures/pumpswap/t429a_idl_pump_amm_onchain.json``); both were
confirmed live: ``fee_config`` (``5PHirr8joyTMp9JMm6nW7hNDVyEYdkzDqazxPD7RaTjx``)
exists and is owned by the Pump Fees program.
"""

from __future__ import annotations

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.solana_codec import (
    TOKEN_PROGRAM_ID,
    associated_token_address,
    find_program_address,
    pubkey_bytes,
)
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID, WSOL_MINT

__all__ = [
    "PUMP_FEE_PROGRAM_ID",
    "coin_creator_vault",
    "event_authority",
    "fee_config_address",
    "pool_address",
    "pool_authority_address",
]

PUMP_FEE_PROGRAM_ID = "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"


def pool_authority_address(mint: str) -> str:
    return find_program_address([b"pool-authority", pubkey_bytes(mint)], PUMP_PROGRAM_ID)[0]


def pool_address(mint: str) -> str:
    """The canonical (index-0) PumpSwap pool a migrated ``mint`` graduated into."""
    authority = pool_authority_address(mint)
    index_bytes = (0).to_bytes(2, "little")
    return find_program_address(
        [
            b"pool",
            index_bytes,
            pubkey_bytes(authority),
            pubkey_bytes(mint),
            pubkey_bytes(WSOL_MINT),
        ],
        PUMPSWAP_PROGRAM_ID,
    )[0]


def event_authority() -> str:
    return find_program_address([b"__event_authority"], PUMPSWAP_PROGRAM_ID)[0]


def fee_config_address() -> str:
    """PumpSwap's own ``FeeConfig`` entry — seeded by *this* program's id, not
    the bonding curve's (confirmed live: exists, owned by the Pump Fees
    program)."""
    return find_program_address(
        [b"fee_config", pubkey_bytes(PUMPSWAP_PROGRAM_ID)], PUMP_FEE_PROGRAM_ID
    )[0]


def coin_creator_vault(coin_creator: str) -> tuple[str, str]:
    """``(coin_creator_vault_authority, coin_creator_vault_ata)`` — the
    authority is a PDA of *this* program (``["creator_vault", coin_creator]``),
    the ATA holds WSOL under the classic SPL Token program."""
    authority = find_program_address(
        [b"creator_vault", pubkey_bytes(coin_creator)], PUMPSWAP_PROGRAM_ID
    )[0]
    ata = associated_token_address(authority, WSOL_MINT, token_program=TOKEN_PROGRAM_ID)
    return authority, ata
