"""``MayhemState`` — the Mayhem program's per-coin account, and the four on-chain
numbers that make a Mayhem curve's denominator honest (T4.2e).

**Why.** T4.2d left every Mayhem curve without a denominator: the fixture
``2sduGq…`` held 822,6 M real tokens, more than the 793,1 M
``initial_real_token_reserves`` of the ``/global-params`` record, and nothing
in ``Global`` names a Mayhem reserve. Five live reads of 12/09/2026
(``tests/fixtures/pumpfun/t42e_rpc_mayhem_accounts*_raw.json``) settle what the
excess is: **the agent's own tokens.** ``create_v2`` mints the coin with the
record's curve *and* a second billion for the agent — the SPL mint's supply
reads 2 000 000 000 while ``BondingCurve.token_total_supply`` still reads
1 000 000 000 — held in ``mayhem_token_vault`` (the ATA of the ``sol-vault``
PDA, which *is* the published agent wallet ``BwWK17c…``); the agent sells from
and buys into that vault, and ``MayhemState`` keeps its net flow. So

    real_token_reserves = initial_real − human_net + agent_net_sold

with ``initial_real`` the record's, for a Mayhem curve as for any other: on
``2sduGq…`` the identity closes to the subunit with ``human_net = 0``
(822 644 036 902 123 = 793 100 000 000 000 + 29 544 036 902 123), and the site's
own progress for ``4BTP…`` (3,43 %) is ``1 − 765 908 543 509 630 / 793,1 M``
(3,4285 %). The record was always the denominator; what T4.2d's guard could not
see was the agent's net supply.

**What is by the IDL and what is not**, because the Mayhem program has no
published IDL (``pump-fun/pump-public-docs`` has none, T4.0d §3.2; its Anchor IDL
account ``Acy6P7…`` = ``create_with_seed(find_program_address([], MAyh),
"anchor:idl", MAyh)`` is absent on chain — ``t42e_rpc_mayhem_idl_raw.json``,
``result.value = null``):

- **by the pump IDL** (``create_v2`` / ``set_mayhem_virtual_params`` accounts):
  the PDA seeds ``["mayhem-state", mint]``, ``["global-params"]`` and
  ``["sol-vault"]`` on the Mayhem program, the vault as the ATA of ``sol-vault``
  under **Token-2022** (``create_v2``'s ``token_program`` is that constant), and
  the ``BondingCurve`` fields (``decode.py``);
- **by Anchor's convention**: ``sha256("account:MayhemState")[:8]`` =
  ``b1fdbf7dcb16866b`` and ``sha256("account:GlobalParams")[:8]`` =
  ``79c1f857c3384c0b`` match the bytes read, which fixes the two account type
  names. ``GlobalParams`` (318 bytes) is kept raw and not interpreted;
- **inferred, and therefore checked on every read**: the field layout below.
  The decoded net flow must satisfy, with no constant in it,

      vault_tokens + agent_net_sold == mint_supply − curve.token_total_supply

  (the extra supply is in the vault or in the curve, nowhere else — held to the
  subunit on 5/5 reads, including ``Fh42k…`` 6,5 h in, whose agent had sold
  999 999 991,75 of its billion), and the mint pubkey inside the account must be
  the mint asked for. A read that fails either is refused, never a number.

Layout (106 bytes, little-endian, Borsh — no alignment):

======  ====  ==========================================================
offset  size  field
======  ====  ==========================================================
0       8     discriminator ``b1fdbf7dcb16866b``
8       8     u64 ``window_start`` (unix s; = the coin's ``created_timestamp``)
16      8     u64 ``window_end`` (= ``window_start + 86 400`` on 5/5: the 24 h)
24      32    pubkey ``mint``
56      16    i128 net lamports the agent paid into the curve (negative: withdrew)
72      16    i128 net subunits the agent sold into the curve (negative: bought)
88      18    tail, not interpreted (a u8, a u64 that reads as a unix second
              ~14 min after creation, a u8 = 1, 8 zero bytes) — kept raw
======  ====  ==========================================================
"""

from __future__ import annotations

import base64
import hashlib
import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.curve import LAMPORTS_PER_SOL, TOKEN_SUBUNITS_PER_TOKEN
from hunter_exchanges.pumpfun.decode import BondingCurveAccount
from hunter_exchanges.pumpfun.models import ReceivedAtMixin
from hunter_exchanges.pumpfun.solana_codec import (
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    associated_token_address,
    b58encode,
    find_program_address,
    pubkey_bytes,
)
from hunter_exchanges.pumpfun.tx import bonding_curve_address

__all__ = [
    "GLOBAL_PARAMS_DISCRIMINATOR",
    "MAYHEM_PROGRAM_ID",
    "MAYHEM_STATE_DISCRIMINATOR",
    "MAYHEM_STATE_LEN",
    "MINTS_PER_BATCH",
    "MayhemPdas",
    "MayhemRefused",
    "MayhemStateAccount",
    "NormalizedMayhemFlow",
    "anchor_account_discriminator",
    "create_with_seed",
    "decode_mayhem_state",
    "decode_mint_supply",
    "decode_token_account_amount",
    "mayhem_accounts_for",
    "mayhem_flow_from_accounts",
    "mayhem_pdas",
    "mayhem_state_address",
    "mayhem_token_vault_address",
]

EXCHANGE = "pumpfun"
MAYHEM_PROGRAM_ID = "MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e"
"""``docs/PUMPFUN-ONCHAIN.md`` §0 — the program ``create_v2`` CPIs into."""


def anchor_account_discriminator(name: str) -> bytes:
    """Anchor's convention: the first 8 bytes of ``sha256("account:<Name>")``."""
    return hashlib.sha256(f"account:{name}".encode()).digest()[:8]


MAYHEM_STATE_DISCRIMINATOR = anchor_account_discriminator("MayhemState")
GLOBAL_PARAMS_DISCRIMINATOR = anchor_account_discriminator("GlobalParams")
MAYHEM_STATE_LEN = 106
_MAYHEM_STATE_MIN_LEN = 88
_TOKEN_ACCOUNT_MIN_LEN = 72
_MINT_MIN_LEN = 82
_MINTS_PER_BATCH = 25
"""``getMultipleAccounts`` takes up to 100 addresses; four per mint."""


def create_with_seed(base: str, seed: str, owner: str) -> str:
    """``Pubkey::create_with_seed``: ``sha256(base || seed || owner)``."""
    digest = hashlib.sha256(pubkey_bytes(base) + seed.encode() + pubkey_bytes(owner)).digest()
    return b58encode(digest)


@dataclass(frozen=True, slots=True)
class MayhemPdas:
    global_params: str
    sol_vault: str
    """``["sol-vault"]`` — the agent wallet ``pump.fun/docs/mayhem-mode`` publishes."""
    idl_account: str
    """Where an Anchor program keeps its IDL; absent for this program (module docstring)."""


@lru_cache(maxsize=1)
def mayhem_pdas() -> MayhemPdas:
    base, _ = find_program_address([], MAYHEM_PROGRAM_ID)
    return MayhemPdas(
        global_params=find_program_address([b"global-params"], MAYHEM_PROGRAM_ID)[0],
        sol_vault=find_program_address([b"sol-vault"], MAYHEM_PROGRAM_ID)[0],
        idl_account=create_with_seed(base, "anchor:idl", MAYHEM_PROGRAM_ID),
    )


def mayhem_state_address(mint: str) -> str:
    return find_program_address([b"mayhem-state", pubkey_bytes(mint)], MAYHEM_PROGRAM_ID)[0]


def mayhem_token_vault_address(mint: str) -> str:
    """The ATA of ``sol-vault`` under Token-2022 — ``create_v2`` fixes that program."""
    return associated_token_address(
        mayhem_pdas().sol_vault, mint, token_program=TOKEN_2022_PROGRAM_ID
    )


def mayhem_accounts_for(mint: str) -> tuple[str, str, str, str]:
    """The four accounts one flow is read from: curve, state, vault, mint."""
    return (
        bonding_curve_address(mint),
        mayhem_state_address(mint),
        mayhem_token_vault_address(mint),
        mint,
    )


@dataclass(frozen=True, slots=True)
class MayhemStateAccount:
    """Raw fields off the account bytes (subunits / lamports, signed where the chain is)."""

    window_start: int
    window_end: int
    mint: str
    agent_net_sol_in_lamports: int
    agent_net_sold_subunits: int
    tail: bytes


def _raw(data_base64: str, *, owner: str, expected_owner: str, what: str) -> bytes:
    if owner != expected_owner:
        raise MalformedMessage(f"{what} owner {owner!r} is not {expected_owner}", exchange=EXCHANGE)
    try:
        return base64.b64decode(data_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise MalformedMessage(f"{what} data is not base64: {exc}", exchange=EXCHANGE) from exc


def decode_mayhem_state(data_base64: str, *, owner: str) -> MayhemStateAccount:
    """Decode a ``MayhemState`` payload; refuses a wrong owner, discriminator or length."""
    raw = _raw(data_base64, owner=owner, expected_owner=MAYHEM_PROGRAM_ID, what="MayhemState")
    if len(raw) < _MAYHEM_STATE_MIN_LEN:
        raise MalformedMessage(
            f"MayhemState too short: {len(raw)} bytes, need >= {_MAYHEM_STATE_MIN_LEN}",
            exchange=EXCHANGE,
        )
    if raw[:8] != MAYHEM_STATE_DISCRIMINATOR:
        raise MalformedMessage("wrong MayhemState discriminator", exchange=EXCHANGE)
    start, end = struct.unpack_from("<QQ", raw, 8)
    return MayhemStateAccount(
        window_start=start,
        window_end=end,
        mint=b58encode(raw[24:56]),
        agent_net_sol_in_lamports=int.from_bytes(raw[56:72], "little", signed=True),
        agent_net_sold_subunits=int.from_bytes(raw[72:88], "little", signed=True),
        tail=bytes(raw[88:]),
    )


def decode_token_account_amount(data_base64: str, *, owner: str) -> int:
    """SPL token account (Token or Token-2022, same 165-byte base): ``amount`` at 64."""
    if owner not in (TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID):
        raise MalformedMessage(
            f"token account owner {owner!r} is not a token program", exchange=EXCHANGE
        )
    raw = _raw(data_base64, owner=owner, expected_owner=owner, what="token account")
    if len(raw) < _TOKEN_ACCOUNT_MIN_LEN:
        raise MalformedMessage("token account too short", exchange=EXCHANGE)
    return struct.unpack_from("<Q", raw, 64)[0]


def decode_mint_supply(data_base64: str, *, owner: str) -> int:
    """SPL mint (Token or Token-2022): ``supply`` at 36, after the ``COption`` authority."""
    if owner not in (TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID):
        raise MalformedMessage(f"mint owner {owner!r} is not a token program", exchange=EXCHANGE)
    raw = _raw(data_base64, owner=owner, expected_owner=owner, what="mint")
    if len(raw) < _MINT_MIN_LEN:
        raise MalformedMessage("mint account too short", exchange=EXCHANGE)
    return struct.unpack_from("<Q", raw, 36)[0]


class MayhemRefused(MalformedMessage):
    """A flow this module will not vouch for, by name: ``mint_mismatch``,
    ``not_mayhem_curve`` or ``identity_failed``."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"mayhem flow refused ({reason}): {detail}", exchange=EXCHANGE)
        self.reason = reason


class NormalizedMayhemFlow(ReceivedAtMixin):
    """One finalized read of a Mayhem coin's four accounts, reconciled.

    Human units (tokens with 6 decimals, SOL); the two agent figures are
    **signed** because the chain's are: a positive ``agent_net_sold_tokens``
    means the agent has put that many of its own tokens into the curve, net.
    """

    kind: Literal["meme_mayhem_flow"] = "meme_mayhem_flow"
    mint: str
    source: str = "solana_rpc"
    slot: int | None = None
    commitment: str | None = None
    window_start: datetime
    window_end: datetime
    curve_real_token_reserves: Decimal
    curve_total_supply: Decimal
    mint_supply: Decimal
    vault_tokens: Decimal
    agent_net_sold_tokens: Decimal
    agent_net_sol_in: Decimal
    curve: BondingCurveAccount
    """The curve account of the same slot, raw, for the caller's snapshot."""

    @property
    def agent_extra_supply(self) -> Decimal:
        """What the agent was minted: the SPL supply beyond the curve's own supply."""
        return self.mint_supply - self.curve_total_supply

    @property
    def curve_reserve_without_agent(self) -> Decimal:
        """``real_token_reserves − agent_net_sold`` = ``initial_real − human_net``:
        the reserve the humans alone account for, never above the initial."""
        return self.curve_real_token_reserves - self.agent_net_sold_tokens


def mayhem_flow_from_accounts(
    mint: str,
    *,
    curve: BondingCurveAccount,
    state: MayhemStateAccount,
    vault_tokens: int,
    mint_supply: int,
    slot: int | None = None,
    commitment: str | None = None,
    now: datetime | None = None,
) -> NormalizedMayhemFlow:
    """Reconcile the four accounts into one flow, or refuse by name."""
    if state.mint != mint:
        raise MayhemRefused("mint_mismatch", f"MayhemState names {state.mint}")
    if not curve.is_mayhem_mode:
        raise MayhemRefused("not_mayhem_curve", "BondingCurve.is_mayhem_mode is false")
    extra = mint_supply - curve.token_total_supply
    if vault_tokens + state.agent_net_sold_subunits != extra:
        raise MayhemRefused(
            "identity_failed",
            f"vault {vault_tokens} + net sold {state.agent_net_sold_subunits} != extra supply {extra}",
        )
    at = now or datetime.now(UTC)
    return NormalizedMayhemFlow(
        mint=mint,
        slot=slot,
        commitment=commitment,
        window_start=datetime.fromtimestamp(state.window_start, tz=UTC),
        window_end=datetime.fromtimestamp(state.window_end, tz=UTC),
        curve_real_token_reserves=Decimal(curve.real_token_reserves) / TOKEN_SUBUNITS_PER_TOKEN,
        curve_total_supply=Decimal(curve.token_total_supply) / TOKEN_SUBUNITS_PER_TOKEN,
        mint_supply=Decimal(mint_supply) / TOKEN_SUBUNITS_PER_TOKEN,
        vault_tokens=Decimal(vault_tokens) / TOKEN_SUBUNITS_PER_TOKEN,
        agent_net_sold_tokens=Decimal(state.agent_net_sold_subunits) / TOKEN_SUBUNITS_PER_TOKEN,
        agent_net_sol_in=Decimal(state.agent_net_sol_in_lamports) / LAMPORTS_PER_SOL,
        curve=curve,
        observed_at=at,
        received_at=at,
    )


MINTS_PER_BATCH = _MINTS_PER_BATCH
