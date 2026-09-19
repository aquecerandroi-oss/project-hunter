"""Generic-mint Jupiter swap verifier (T4.73) — the instruction-by-instruction
discipline of ``treasury_verify.verify_swap_transaction`` (USDC -> SOL only,
T4.54b), generalized to any input/output mint pair for
``infra/scripts/meme_spot_swap.py``.

Kept as its own module rather than folded into ``treasury_verify.py``: that
file backs the live, already-reviewed USDC -> SOL treasury path
(``docs/RISK_ENGINE_MEME.md`` §16, ``.claude/state/review-T4.54.md``) and this
task must not risk it — every existing test there is untouched. This module
shares only the public constants (``JUP_PROGRAM_ID``, ``TreasurySwapRefused``,
``MAX_PRIORITY_FEE_LAMPORTS``, the two Anchor route discriminators) and
duplicates the small instruction checks that are mint-agnostic already.

Rules:

- ComputeBudget: only ``SetComputeUnitLimit``/``SetComputeUnitPrice``, once
  each, no accounts, ``limit x price`` within ``MAX_PRIORITY_FEE_LAMPORTS``.
- AssociatedToken: only ``Create``/``CreateIdempotent``, paid and owned by the
  wallet, at most ``MAX_ATA_CREATES`` — of **either** mint's ATA (the "both
  ATA" case: a token->token swap creates both sides' accounts).
- Token/Token-2022: only ``CloseAccount``, ``SyncNative`` and
  ``InitializeAccount*`` on the wallet's own **WSOL** ATA — wrap/unwrap is the
  only reason a Token instruction appears outside JUP6's own CPI; refused for
  every other account or mint.
- System: only a ``Transfer(wallet -> own WSOL ATA, == in_amount)``, and only
  when the input mint is WSOL (wrapping SOL to spend it); refused otherwise
  (a plain token->token or token->SOL swap needs no System instruction at
  all).
- JUP6: exactly one ``route``/``shared_accounts_route``, wallet authority,
  source = the wallet's input-mint ATA, destination = the wallet's
  output-mint ATA, no third-party destination, no platform fee;
  ``in_amount == requested``, ``quoted_out_amount >= requested minimum``,
  ``slippage_bps <= cap``.
- any other program, or any instruction this module cannot decode, is
  refused by name.

**Known limits**, both fail-closed: the route's ATA addresses are derived
assuming the legacy Token program for both mints (a Token-2022 mint on either
leg is refused, not silently mistrusted — ``route_source_mismatch``/
``route_destination_mismatch``); and, as in ``treasury_verify``, the route's
fixed args are read from the instruction's tail, so the caller must still run
the post-simulation balance invariant before signing.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from hunter_exchanges.jupiter.models import WRAPPED_SOL_MINT
from hunter_exchanges.jupiter.versioned_tx import VersionedCompiledInstruction, VersionedMessage
from hunter_exchanges.pumpfun.solana_codec import (
    ASSOCIATED_TOKEN_PROGRAM_ID,
    COMPUTE_BUDGET_PROGRAM_ID,
    SYSTEM_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    associated_token_address,
    pubkey_bytes,
)
from hunter_meme_executor.treasury_rules import JUP_PROGRAM_ID, TreasurySwapRefused
from hunter_meme_executor.treasury_verify import (
    MAX_ATA_CREATES,
    MAX_PRIORITY_FEE_LAMPORTS,
    MAX_ROUTE_STEPS,
    ROUTE_DISCRIMINATOR,
    SHARED_ACCOUNTS_ROUTE_DISCRIMINATOR,
)

__all__ = ["SpotSwapIntent", "VerifiedSpotSwap", "verify_spot_swap_tx"]

_ROUTE_ARGS = struct.Struct("<QQHB")  # in_amount, quoted_out_amount, slippage_bps, platform_fee_bps
_ZERO_BLOCKHASH_B58 = "1" * 32

# (kind, accounts-offset of the vec, authority, source, destination, third-party dest, fee)
_ROUTE_LAYOUT = {
    ROUTE_DISCRIMINATOR: ("route", 8, 1, 2, 3, 4, 6),
    SHARED_ACCOUNTS_ROUTE_DISCRIMINATOR: ("shared_accounts_route", 9, 2, 3, 6, None, 9),
}


@dataclass(frozen=True, slots=True)
class SpotSwapIntent:
    wallet: str
    input_mint: str
    output_mint: str
    in_amount: int
    min_quoted_out: int
    """The quote's own ``out_amount`` — the instruction may promise more, never less."""
    max_slippage_bps: int


@dataclass(frozen=True, slots=True)
class VerifiedSpotSwap:
    route_kind: str
    in_amount: int
    quoted_out_amount: int
    slippage_bps: int
    priority_fee_lamports: int
    ata_creates: int
    wraps_sol: bool
    unwraps_sol: bool


@dataclass(slots=True)
class _Seen:
    route: tuple[str, int, int, int] | None = None
    limit: int | None = None
    price: int | None = None
    ata_creates: int = 0
    wrap_transfer_seen: bool = False
    close_account_seen: bool = False


def _key(message: VersionedMessage, ix: VersionedCompiledInstruction, position: int) -> str | None:
    if position >= len(ix.account_indexes):
        return None
    return message.program_id(ix.account_indexes[position])


def _compute_budget(ix: VersionedCompiledInstruction, seen: _Seen) -> None:
    if ix.account_indexes:
        raise TreasurySwapRefused("compute_budget_with_accounts")
    if len(ix.data) == 5 and ix.data[0] == 2:
        if seen.limit is not None:
            raise TreasurySwapRefused("duplicate_compute_unit_limit")
        seen.limit = struct.unpack("<I", ix.data[1:5])[0]
        return
    if len(ix.data) == 9 and ix.data[0] == 3:
        if seen.price is not None:
            raise TreasurySwapRefused("duplicate_compute_unit_price")
        seen.price = struct.unpack("<Q", ix.data[1:9])[0]
        return
    raise TreasurySwapRefused("compute_budget_unknown_instruction")


def _create_ata(
    message: VersionedMessage, ix: VersionedCompiledInstruction, wallet: str, seen: _Seen
) -> None:
    if ix.data not in (b"", b"\x00", b"\x01"):
        raise TreasurySwapRefused("ata_instruction_not_create")
    if len(ix.account_indexes) != 6:
        raise TreasurySwapRefused("ata_instruction_account_count")
    if _key(message, ix, 0) != wallet:
        raise TreasurySwapRefused("ata_payer_not_wallet")
    if _key(message, ix, 2) != wallet:
        raise TreasurySwapRefused("ata_owner_not_wallet")
    if _key(message, ix, 4) != SYSTEM_PROGRAM_ID:
        raise TreasurySwapRefused("ata_system_program_mismatch")
    token_program = _key(message, ix, 5)
    if token_program not in (TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID):
        raise TreasurySwapRefused("ata_token_program_mismatch")
    mint = _key(message, ix, 3)
    ata = _key(message, ix, 1)
    if mint is None or ata is None:
        # T4.73b (review finding 6): an address only reachable through a lookup
        # table cannot be checked here, so it is refused — never skipped.
        raise TreasurySwapRefused("ata_account_via_lookup_table")
    if ata != associated_token_address(wallet, mint, token_program=token_program):
        raise TreasurySwapRefused("ata_address_mismatch")
    seen.ata_creates += 1
    if seen.ata_creates > MAX_ATA_CREATES:
        raise TreasurySwapRefused("too_many_ata_creates")


def _wsol_token(
    message: VersionedMessage,
    ix: VersionedCompiledInstruction,
    wallet: str,
    wsol_ata: str | None,
    seen: _Seen,
) -> None:
    if not ix.data:
        raise TreasurySwapRefused("token_instruction_undecodable")
    discriminator = ix.data[0]
    if wsol_ata is None:
        raise TreasurySwapRefused(f"token_instruction_not_allowed:{discriminator}")
    if discriminator == 9:  # CloseAccount [account, destination, owner]
        if len(ix.data) != 1 or len(ix.account_indexes) < 3:
            raise TreasurySwapRefused("close_account_malformed")
        if _key(message, ix, 0) != wsol_ata:
            raise TreasurySwapRefused("close_account_not_wsol_ata")
        if _key(message, ix, 1) != wallet:
            raise TreasurySwapRefused("close_account_destination_not_wallet")
        if _key(message, ix, 2) != wallet:
            raise TreasurySwapRefused("close_account_owner_not_wallet")
        if seen.close_account_seen:
            raise TreasurySwapRefused("more_than_one_close_account")
        seen.close_account_seen = True
        return
    if discriminator == 17:  # SyncNative [account]
        if _key(message, ix, 0) != wsol_ata:
            raise TreasurySwapRefused("sync_native_not_wsol_ata")
        return
    if discriminator in (1, 16, 18):  # InitializeAccount / 2 / 3
        if _key(message, ix, 0) != wsol_ata:
            raise TreasurySwapRefused("initialize_account_not_wsol_ata")
        owner_ok = (
            _key(message, ix, 2) == wallet
            if discriminator == 1
            else ix.data[1:33] == pubkey_bytes(wallet)
        )
        if not owner_ok:
            raise TreasurySwapRefused("initialize_account_owner_not_wallet")
        return
    raise TreasurySwapRefused(f"token_instruction_not_allowed:{discriminator}")


def _system_wrap(
    message: VersionedMessage,
    ix: VersionedCompiledInstruction,
    wallet: str,
    wsol_ata: str | None,
    in_amount: int,
    seen: _Seen,
) -> None:
    if wsol_ata is None or len(ix.data) != 12 or struct.unpack_from("<I", ix.data, 0)[0] != 2:
        raise TreasurySwapRefused("system_instruction_not_allowed")
    if len(ix.account_indexes) != 2:
        raise TreasurySwapRefused("system_transfer_account_count")
    if _key(message, ix, 0) != wallet:
        raise TreasurySwapRefused("system_transfer_source_not_wallet")
    if _key(message, ix, 1) != wsol_ata:
        raise TreasurySwapRefused("system_transfer_destination_not_wsol_ata")
    amount = struct.unpack_from("<Q", ix.data, 4)[0]
    if amount != in_amount:
        raise TreasurySwapRefused(f"system_transfer_amount_mismatch:{amount}!={in_amount}")
    if seen.wrap_transfer_seen:
        raise TreasurySwapRefused("more_than_one_system_transfer")
    seen.wrap_transfer_seen = True


def _route(
    message: VersionedMessage,
    ix: VersionedCompiledInstruction,
    intent: SpotSwapIntent,
    seen: _Seen,
) -> None:
    if seen.route is not None:
        raise TreasurySwapRefused("more_than_one_route_instruction")
    layout = _ROUTE_LAYOUT.get(ix.data[:8])
    if layout is None:
        raise TreasurySwapRefused(f"route_instruction_unknown:{ix.data[:8].hex()}")
    kind, vec_offset, authority, source, destination, third_party, fee_account = layout
    if len(ix.data) < vec_offset + 4 + _ROUTE_ARGS.size:
        raise TreasurySwapRefused("route_data_truncated")
    steps = struct.unpack_from("<I", ix.data, vec_offset)[0]
    if not 1 <= steps <= MAX_ROUTE_STEPS:
        raise TreasurySwapRefused(f"route_plan_length_invalid:{steps}")
    if len(ix.data) < vec_offset + 4 + 4 * steps + _ROUTE_ARGS.size:
        raise TreasurySwapRefused("route_data_truncated")
    in_amount, quoted_out, slippage_bps, platform_fee_bps = _ROUTE_ARGS.unpack(
        ix.data[-_ROUTE_ARGS.size :]
    )
    if in_amount != intent.in_amount:
        raise TreasurySwapRefused(f"route_in_amount_mismatch:{in_amount}!={intent.in_amount}")
    if quoted_out < intent.min_quoted_out:
        raise TreasurySwapRefused("route_quoted_out_below_quote")
    if slippage_bps > intent.max_slippage_bps:
        raise TreasurySwapRefused(f"route_slippage_above_cap:{slippage_bps}")
    if platform_fee_bps != 0:
        raise TreasurySwapRefused("route_platform_fee_present")
    source_ata = associated_token_address(
        intent.wallet, intent.input_mint, token_program=TOKEN_PROGRAM_ID
    )
    dest_ata = associated_token_address(
        intent.wallet, intent.output_mint, token_program=TOKEN_PROGRAM_ID
    )
    if len(ix.account_indexes) <= fee_account:
        raise TreasurySwapRefused("route_account_count")
    for position in (authority, source, destination, third_party, fee_account):
        if position is not None and _key(message, ix, position) is None:
            raise TreasurySwapRefused("route_account_via_lookup_table")
    if _key(message, ix, authority) != intent.wallet:
        raise TreasurySwapRefused("route_authority_not_wallet")
    if _key(message, ix, source) != source_ata:
        raise TreasurySwapRefused("route_source_mismatch")
    if _key(message, ix, destination) != dest_ata:
        raise TreasurySwapRefused("route_destination_mismatch")
    if third_party is not None and _key(message, ix, third_party) != JUP_PROGRAM_ID:
        raise TreasurySwapRefused("route_third_party_destination")
    if _key(message, ix, fee_account) != JUP_PROGRAM_ID:
        raise TreasurySwapRefused("route_platform_fee_account_present")
    seen.route = (kind, in_amount, quoted_out, slippage_bps)


def verify_spot_swap_tx(message: VersionedMessage, *, intent: SpotSwapIntent) -> VerifiedSpotSwap:
    """The module docstring's discipline for any ``(input_mint, output_mint)``."""
    wallet = intent.wallet
    if message.num_required_signatures != 1:
        raise TreasurySwapRefused("more_than_one_signer")
    if not message.static_account_keys or message.static_account_keys[0] != wallet:
        raise TreasurySwapRefused("fee_payer_not_wallet")
    if message.recent_blockhash == _ZERO_BLOCKHASH_B58:
        raise TreasurySwapRefused("blockhash_missing")
    wraps_sol = intent.input_mint == WRAPPED_SOL_MINT
    unwraps_sol = intent.output_mint == WRAPPED_SOL_MINT
    if wraps_sol and unwraps_sol:
        raise TreasurySwapRefused("both_legs_are_wsol")
    wsol_ata = (
        associated_token_address(wallet, WRAPPED_SOL_MINT, token_program=TOKEN_PROGRAM_ID)
        if (wraps_sol or unwraps_sol)
        else None
    )
    seen = _Seen()
    for ix in message.instructions:
        program = message.program_id(ix.program_id_index)
        if program is None:
            raise TreasurySwapRefused("program_via_lookup_table")
        if program == COMPUTE_BUDGET_PROGRAM_ID:
            _compute_budget(ix, seen)
        elif program == ASSOCIATED_TOKEN_PROGRAM_ID:
            _create_ata(message, ix, wallet, seen)
        elif program in (TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID):
            _wsol_token(message, ix, wallet, wsol_ata, seen)
        elif program == JUP_PROGRAM_ID:
            _route(message, ix, intent, seen)
        elif program == SYSTEM_PROGRAM_ID:
            if not wraps_sol:
                raise TreasurySwapRefused("system_program_not_allowed")
            _system_wrap(message, ix, wallet, wsol_ata, intent.in_amount, seen)
        else:
            raise TreasurySwapRefused(f"program_not_allowed:{program}")
    if seen.route is None:
        raise TreasurySwapRefused("route_instruction_missing")
    limit = 1_400_000 if seen.limit is None else seen.limit
    priority_fee = -(-limit * (seen.price or 0) // 1_000_000)
    if priority_fee > MAX_PRIORITY_FEE_LAMPORTS:
        raise TreasurySwapRefused(f"priority_fee_above_cap:{priority_fee}")
    kind, in_amount, quoted_out, slippage_bps = seen.route
    return VerifiedSpotSwap(
        route_kind=kind,
        in_amount=in_amount,
        quoted_out_amount=quoted_out,
        slippage_bps=slippage_bps,
        priority_fee_lamports=priority_fee,
        ata_creates=seen.ata_creates,
        wraps_sol=wraps_sol,
        unwraps_sol=unwraps_sol,
    )
