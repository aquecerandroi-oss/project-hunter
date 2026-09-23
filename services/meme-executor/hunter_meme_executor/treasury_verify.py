"""T4.54b fix A — the instruction-by-instruction verifier of a Jupiter swap
(USDC -> SOL) before it is ever signed. Pure: a decoded ``VersionedMessage``
and a ``SwapIntent`` in, a ``VerifiedSwap`` out, or a named refusal.

What Jupiter actually emits for USDC -> SOL with ``wrapAndUnwrapSol`` (real
capture, 18/09/2026, ``POST lite-api.jup.ag/swap/v1/swap`` for this wallet's
public key, 1 USDC, ``tests/fixtures/jupiter_swap_usdc_to_sol_real.json``):
``ComputeBudget.SetComputeUnitLimit``, ``ComputeBudget.SetComputeUnitPrice``,
``AssociatedToken.CreateIdempotent`` (the wallet's own WSOL ATA; the mint
sits behind the lookup table), ``JUP6.route`` and ``Token.CloseAccount`` of
that WSOL ATA back to the wallet. **No System instruction**: the wrap side
(``SystemProgram.Transfer`` into the WSOL ATA + ``SyncNative``) only exists
when SOL is the *input*, which the treasury never does — so System is refused
outright, as ``docs/RISK_ENGINE_MEME.md`` §16 documents.

**Address lookup tables (T4.83).** Jupiter reaches accounts — the route's, and
the mint of that ``CreateIdempotent`` — through ALTs; the capture above has one
table and its ATA mint is account index 18. Until T4.83 this module refused
what it could not see (``route_account_via_lookup_table``) and, worse,
*skipped* the ATA derivation when the mint was loaded. Now the caller
(``treasury_send``) resolves the tables first — IO, ``spot_alt.account_keys_for``,
one ``getMultipleAccounts`` at ``finalized`` — and hands the resolved
``account_keys`` in; this module stays pure and checks a loaded address exactly
like a static one. Nothing is ever skipped: the ATA derivation is mandatory and
refuses by name when an account cannot be resolved.

Discipline, mirroring ``hunter_exchanges.pumpfun.verify``:

- ComputeBudget: only ``SetComputeUnitLimit``/``SetComputeUnitPrice``, once
  each, no accounts, and ``limit × price`` within ``MAX_PRIORITY_FEE_LAMPORTS``;
- AssociatedToken: only ``Create``/``CreateIdempotent`` paid by the wallet,
  owned by the wallet, ``MAX_ATA_CREATES`` at most (rent-bounded);
- Token / Token-2022: only ``CloseAccount``, ``SyncNative`` and
  ``InitializeAccount*`` on the wallet's own WSOL ATA, destination/owner the
  wallet (the discriminator is decoded, never guessed);
- ``JUP6``: exactly one ``route`` or ``shared_accounts_route`` (Anchor
  discriminator), user authority the wallet, source the wallet's USDC ATA,
  destination the wallet's WSOL ATA, no third-party destination and no
  platform-fee account; ``in_amount == usdc_atoms``, ``quoted_out_amount >=``
  the quote's, ``slippage_bps <= cap``, ``platform_fee_bps == 0``;
- any other program, or any instruction this module cannot decode, is refused.

**Known limit.** ``route``'s fixed args come *after* a ``Vec<RoutePlanStep>``
whose ``Swap`` enum has 100+ variants with differing payloads; decoding the
plan itself would go stale with every new AMM. The args are therefore read
from the **tail** (the last 19 bytes), which is where Anchor's Borsh layout
puts them for a well-formed plan — but Anchor tolerates trailing bytes, so a
hostile builder could append a fake tail. That is why the caller also runs
the post-simulation balance invariant (``treasury_rules.check_simulated_balances``):
the chain's own dry run, not this decode, is the last word on how much USDC
leaves and how much SOL arrives.
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Sequence
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
from hunter_meme_executor.spot_alt import account_at as _key
from hunter_meme_executor.spot_alt import validated_account_keys
from hunter_meme_executor.treasury_rules import JUP_PROGRAM_ID, USDC_MINT, TreasurySwapRefused

__all__ = [
    "MAX_ATA_CREATES",
    "MAX_PRIORITY_FEE_LAMPORTS",
    "MAX_ROUTE_STEPS",
    "ROUTE_DISCRIMINATOR",
    "SHARED_ACCOUNTS_ROUTE_DISCRIMINATOR",
    "SwapIntent",
    "VerifiedSwap",
    "verify_swap_transaction",
]

MAX_PRIORITY_FEE_LAMPORTS = 5_000_000
"""0,005 SOL — Jupiter's own ceiling for ``prioritizationFeeLamports: "auto"``."""
MAX_ATA_CREATES = 3
MAX_ROUTE_STEPS = 8
_ROUTE_ARGS = struct.Struct("<QQHB")  # in_amount, quoted_out_amount, slippage_bps, platform_fee_bps
_ZERO_BLOCKHASH_B58 = "1" * 32


def _anchor_discriminator(name: str) -> bytes:
    return hashlib.sha256(f"global:{name}".encode()).digest()[:8]


ROUTE_DISCRIMINATOR = _anchor_discriminator("route")
SHARED_ACCOUNTS_ROUTE_DISCRIMINATOR = _anchor_discriminator("shared_accounts_route")

# (accounts-offset of the vec, authority, source, destination, third-party destination, fee)
_ROUTE_LAYOUT = {
    ROUTE_DISCRIMINATOR: ("route", 8, 1, 2, 3, 4, 6),
    SHARED_ACCOUNTS_ROUTE_DISCRIMINATOR: ("shared_accounts_route", 9, 2, 3, 6, None, 9),
}


@dataclass(frozen=True, slots=True)
class SwapIntent:
    wallet: str
    usdc_atoms: int
    min_quoted_out_lamports: int
    """``quote.out_amount`` — the instruction may promise more, never less."""
    max_slippage_bps: int


@dataclass(frozen=True, slots=True)
class VerifiedSwap:
    route_kind: str
    in_amount: int
    quoted_out_amount: int
    slippage_bps: int
    compute_unit_limit: int | None
    compute_unit_price_micro_lamports: int | None
    priority_fee_lamports: int
    ata_creates: int
    closes_wsol_ata: bool


@dataclass(slots=True)
class _Seen:
    route: tuple[str, int, int, int] | None = None
    limit: int | None = None
    price: int | None = None
    ata_creates: int = 0
    closes_wsol_ata: bool = False


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
    keys: Sequence[str], ix: VersionedCompiledInstruction, wallet: str, seen: _Seen
) -> None:
    if ix.data not in (b"", b"\x00", b"\x01"):
        raise TreasurySwapRefused("ata_instruction_not_create")
    if len(ix.account_indexes) != 6:
        raise TreasurySwapRefused("ata_instruction_account_count")
    if _key(keys, ix, 0) != wallet:
        raise TreasurySwapRefused("ata_payer_not_wallet")
    if _key(keys, ix, 2) != wallet:
        raise TreasurySwapRefused("ata_owner_not_wallet")
    if _key(keys, ix, 4) != SYSTEM_PROGRAM_ID:
        raise TreasurySwapRefused("ata_system_program_mismatch")
    token_program = _key(keys, ix, 5)
    if token_program not in (TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID):
        raise TreasurySwapRefused("ata_token_program_mismatch")
    mint, ata = _key(keys, ix, 3), _key(keys, ix, 1)
    # T4.83: never skipped. The account count above already guarantees both
    # positions exist; this refuses by name instead of trusting a ``None``.
    if mint is None or ata is None:
        raise TreasurySwapRefused("ata_accounts_unresolved")
    if ata != associated_token_address(wallet, mint, token_program=token_program):
        raise TreasurySwapRefused("ata_address_mismatch")
    seen.ata_creates += 1
    if seen.ata_creates > MAX_ATA_CREATES:
        raise TreasurySwapRefused("too_many_ata_creates")


def _token(
    keys: Sequence[str],
    ix: VersionedCompiledInstruction,
    program: str,
    wallet: str,
    seen: _Seen,
) -> None:
    if not ix.data:
        raise TreasurySwapRefused("token_instruction_undecodable")
    wsol_ata = associated_token_address(wallet, WRAPPED_SOL_MINT, token_program=program)
    discriminator = ix.data[0]
    if discriminator == 9:  # CloseAccount [account, destination, owner]
        if len(ix.data) != 1 or len(ix.account_indexes) < 3:
            raise TreasurySwapRefused("close_account_malformed")
        if _key(keys, ix, 0) != wsol_ata:
            raise TreasurySwapRefused("close_account_not_wsol_ata")
        if _key(keys, ix, 1) != wallet:
            raise TreasurySwapRefused("close_account_destination_not_wallet")
        if _key(keys, ix, 2) != wallet:
            raise TreasurySwapRefused("close_account_owner_not_wallet")
        if seen.closes_wsol_ata:
            raise TreasurySwapRefused("more_than_one_close_account")
        seen.closes_wsol_ata = True
        return
    if discriminator == 17:  # SyncNative [account]
        if _key(keys, ix, 0) != wsol_ata:
            raise TreasurySwapRefused("sync_native_not_wsol_ata")
        return
    if discriminator in (1, 16, 18):  # InitializeAccount / 2 / 3
        if _key(keys, ix, 0) != wsol_ata:
            raise TreasurySwapRefused("initialize_account_not_wsol_ata")
        owner_ok = (
            _key(keys, ix, 2) == wallet
            if discriminator == 1
            else ix.data[1:33] == pubkey_bytes(wallet)
        )
        if not owner_ok:
            raise TreasurySwapRefused("initialize_account_owner_not_wallet")
        return
    raise TreasurySwapRefused(f"token_instruction_not_allowed:{discriminator}")


def _route(
    keys: Sequence[str],
    ix: VersionedCompiledInstruction,
    intent: SwapIntent,
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
    if in_amount != intent.usdc_atoms:
        raise TreasurySwapRefused(f"route_in_amount_mismatch:{in_amount}!={intent.usdc_atoms}")
    if quoted_out < intent.min_quoted_out_lamports:
        raise TreasurySwapRefused("route_quoted_out_below_quote")
    if slippage_bps > intent.max_slippage_bps:
        raise TreasurySwapRefused(f"route_slippage_above_cap:{slippage_bps}")
    if platform_fee_bps != 0:
        raise TreasurySwapRefused("route_platform_fee_present")
    usdc_ata = associated_token_address(intent.wallet, USDC_MINT, token_program=TOKEN_PROGRAM_ID)
    wsol_ata = associated_token_address(
        intent.wallet, WRAPPED_SOL_MINT, token_program=TOKEN_PROGRAM_ID
    )
    if len(ix.account_indexes) <= fee_account:
        raise TreasurySwapRefused("route_account_count")
    # T4.83: a position that does not exist is a malformed route, not an
    # account "behind a table" — every index is resolved against ``keys``.
    for position in (authority, source, destination, third_party, fee_account):
        if position is not None and _key(keys, ix, position) is None:
            raise TreasurySwapRefused("route_account_count")
    if _key(keys, ix, authority) != intent.wallet:
        raise TreasurySwapRefused("route_authority_not_wallet")
    if _key(keys, ix, source) != usdc_ata:
        raise TreasurySwapRefused("route_source_not_usdc_ata")
    if _key(keys, ix, destination) != wsol_ata:
        raise TreasurySwapRefused("route_destination_not_wsol_ata")
    if third_party is not None and _key(keys, ix, third_party) != JUP_PROGRAM_ID:
        raise TreasurySwapRefused("route_third_party_destination")
    if _key(keys, ix, fee_account) != JUP_PROGRAM_ID:
        raise TreasurySwapRefused("route_platform_fee_account_present")
    seen.route = (kind, in_amount, quoted_out, slippage_bps)


def verify_swap_transaction(
    message: VersionedMessage,
    *,
    intent: SwapIntent,
    account_keys: Sequence[str] | None = None,
) -> VerifiedSwap:
    """§9.1's discipline for a versioned Jupiter swap (module docstring).

    ``account_keys`` is the caller's resolved key list (``spot_alt`` reads the
    lookup tables at ``finalized``); a message without lookup tables needs
    none, and a message with them is refused (``lookup_tables_unresolved``)
    rather than verified half-blind."""
    wallet = intent.wallet
    keys = validated_account_keys(message, account_keys)
    if message.num_required_signatures != 1:
        raise TreasurySwapRefused("more_than_one_signer")
    if not message.static_account_keys or message.static_account_keys[0] != wallet:
        raise TreasurySwapRefused("fee_payer_not_wallet")
    if message.recent_blockhash == _ZERO_BLOCKHASH_B58:
        raise TreasurySwapRefused("blockhash_missing")
    seen = _Seen()
    for ix in message.instructions:
        # ``validated_account_keys`` already refused a program id that is not a
        # static key (``program_via_lookup_table``), as the runtime's own
        # ``sanitize`` requires.
        program = message.static_account_keys[ix.program_id_index]
        if program == COMPUTE_BUDGET_PROGRAM_ID:
            _compute_budget(ix, seen)
        elif program == ASSOCIATED_TOKEN_PROGRAM_ID:
            _create_ata(keys, ix, wallet, seen)
        elif program in (TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID):
            _token(keys, ix, program, wallet, seen)
        elif program == JUP_PROGRAM_ID:
            _route(keys, ix, intent, seen)
        elif program == SYSTEM_PROGRAM_ID:
            raise TreasurySwapRefused("system_program_not_allowed")
        else:
            raise TreasurySwapRefused(f"program_not_allowed:{program}")
    if seen.route is None:
        raise TreasurySwapRefused("route_instruction_missing")
    limit = 1_400_000 if seen.limit is None else seen.limit
    priority_fee = -(-limit * (seen.price or 0) // 1_000_000)
    if priority_fee > MAX_PRIORITY_FEE_LAMPORTS:
        raise TreasurySwapRefused(f"priority_fee_above_cap:{priority_fee}")
    kind, in_amount, quoted_out, slippage_bps = seen.route
    return VerifiedSwap(
        route_kind=kind,
        in_amount=in_amount,
        quoted_out_amount=quoted_out,
        slippage_bps=slippage_bps,
        compute_unit_limit=seen.limit,
        compute_unit_price_micro_lamports=seen.price,
        priority_fee_lamports=priority_fee,
        ata_creates=seen.ata_creates,
        closes_wsol_ata=seen.closes_wsol_ata,
    )
