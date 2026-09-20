"""The pure half of ``meme_close_atas.py`` (T4.77): read a wallet's token
accounts (``getTokenAccountsByOwner``, ``jsonParsed``, Token program **and**
Token-2022), give every account a named verdict, select the ones whose rent
can be recovered, cut them into batches and build the message a batch signs.

Verdicts (one per listed account, all printed in the dry-run table):

- ``close`` — a token **account** (parsed ``type == "account"``, never a
  mint or a multisig), owned by the wallet, ``amount == 0``, not frozen, no
  delegate, close authority absent or the wallet itself, the associated
  token address of (wallet, mint) derived with **its own** token program in
  the seeds, and (for the native WSOL account) no lamports beyond the
  rent-exempt reserve. Token program always; Token-2022 only with
  ``token_2022=True`` (T4.77b, ``--token-2022``) **and** extensions ⊆
  ``{immutableOwner}``;
- ``skipped:token_2022`` — Token-2022 without the opt-in: listed, never
  closed;
- ``skipped:token_2022_extension:<name>`` — Token-2022 with an extension
  outside the reviewed set (transfer fee, confidential transfer, memo, CPI
  guard, transfer hook, ``unparseableExtension``…): ``amount == 0`` alone
  does not prove there is nothing withheld or confidential in it;
- ``skipped:space_mismatch:<space>`` — the on-chain data length is not the
  one the declared extensions imply (165 bytes bare; 166 + Σ(4 + size) with
  extensions — 170 for ``immutableOwner`` alone). Astra (T4.77b re-review):
  the RPC decoder enumerates the TLV with ``unwrap_or_default()``, so an
  extension it does not know comes back as an EMPTY list, not as
  ``unparseableExtension``; ``space`` is a fact of the account the decoder
  cannot shrink, and an undeclared extension is always extra bytes;
- ``skipped:not_token_account:<type>`` — a mint or a multisig; Token-2022's
  ``CloseAccount`` can close a mint, and this script never asks it to;
- ``skipped:proof_run_token_2022_only`` — a classic ``close`` deferred by
  the first ``--token-2022`` run, which closes exactly one Token-2022
  account so the operator proves it on mainnet before the batches of 8;
- ``skipped:nonzero_balance`` — dust is never closed (the program would
  refuse ``NonNativeHasBalance`` anyway; we do not even build it);
- ``skipped:authority_mismatch`` — owner, delegate or close authority is not
  the wallet;
- ``skipped:frozen`` — ``state != initialized``;
- ``skipped:wsol_holds_lamports`` — the native account carries SOL beyond
  its reserve (closing it would still refund everything to the wallet, but
  "empty" was the contract, so it is left alone and named);
- ``skipped:not_ata`` — a token account of the wallet that is not its
  associated token address for that mint (Astra, T4.77 review: an auxiliary
  account some other integration keeps at a fixed address is not rent to
  recover);
- ``skipped:no_rent`` — nothing to recover.

Decimal for SOL, ``int`` lamports; no network in this module except
:func:`list_token_accounts`, which takes the RPC client as an argument.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from meme_close_atas_verify import ALLOWED_TOKEN_PROGRAMS, MAX_CLOSES_PER_BATCH

from hunter_exchanges.pumpfun.close_ata import CLOSE_ACCOUNT_DISCRIMINATOR
from hunter_exchanges.pumpfun.solana_codec import (
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    AccountMeta,
    Instruction,
    Message,
    associated_token_address,
    compile_message,
    set_compute_unit_limit,
    set_compute_unit_price,
)

__all__ = [
    "ALLOWED_EXTENSIONS_2022",
    "BASE_ACCOUNT_LEN",
    "BATCH_SIZE",
    "CU_PER_CLOSE",
    "CU_BASE",
    "Plan",
    "TokenAccountRow",
    "batches",
    "build_batch_message",
    "build_plan",
    "classify",
    "expected_space",
    "format_table",
    "list_token_accounts",
    "parse_token_accounts",
]

BATCH_SIZE = MAX_CLOSES_PER_BATCH
CU_PER_CLOSE = 5_000  # a CloseAccount costs ~2 900 CU on mainnet; headroom, never tight
CU_BASE = 5_000
LAMPORTS = Decimal(1_000_000_000)
# The only Token-2022 extension reviewed for this close (Astra, T4.77): the
# desk's pump.fun ATAs carry it and nothing else. It does not change what
# ``CloseAccount`` does; anything not in this set is skipped by name.
ALLOWED_EXTENSIONS_2022 = frozenset({"immutableOwner"})
# TLV payload size per allowed extension (bytes after the 4-byte type+length header).
_EXTENSION_SIZE = {"immutableOwner": 0}
BASE_ACCOUNT_LEN = 165  # SPL token account, both programs
_ACCOUNT_TYPE_LEN = 1  # Token-2022 appends an AccountType byte when it has extensions
_TLV_HEADER_LEN = 4
_PROGRAM_LABEL = {TOKEN_PROGRAM_ID: "token", TOKEN_2022_PROGRAM_ID: "token-2022"}


class Rpc(Protocol):
    def call(self, method: str, params: list[Any]) -> Any: ...


@dataclass(frozen=True, slots=True)
class TokenAccountRow:
    address: str
    mint: str
    owner: str
    program: str
    lamports: int
    amount: int
    is_native: bool
    rent_exempt_reserve: int | None
    delegate: str | None
    close_authority: str | None
    state: str
    kind: str  # parsed ``type``: account | mint | multisig
    extensions: tuple[str, ...]  # Token-2022 extension names; () on the classic program
    space: int  # on-chain data length, bytes


@dataclass(frozen=True, slots=True)
class Plan:
    wallet: str
    rows: tuple[tuple[TokenAccountRow, str], ...]
    selected: tuple[TokenAccountRow, ...]

    @property
    def total_recoverable(self) -> int:
        return sum(r.lamports for r in self.selected)

    @property
    def skipped(self) -> dict[str, int]:
        counts = Counter(v.removeprefix("skipped:") for _, v in self.rows if v != "close")
        return dict(sorted(counts.items()))


def parse_token_accounts(
    value: Sequence[Mapping[str, Any]], *, program: str
) -> tuple[TokenAccountRow, ...]:
    """The ``value`` list of a ``jsonParsed`` ``getTokenAccountsByOwner``.
    A row this cannot read refuses the whole listing (``ValueError``) — a
    close is never built from a guess."""
    rows: list[TokenAccountRow] = []
    for entry in value:
        try:
            account = entry["account"]
            parsed = account["data"]["parsed"]
            info = parsed["info"]
            reserve = info.get("rentExemptReserve")
            rows.append(
                TokenAccountRow(
                    address=str(entry["pubkey"]),
                    mint=str(info["mint"]),
                    owner=str(info["owner"]),
                    program=str(account["owner"]),
                    lamports=int(account["lamports"]),
                    amount=int(str(info["tokenAmount"]["amount"])),
                    is_native=bool(info.get("isNative", False)),
                    rent_exempt_reserve=None if reserve is None else int(str(reserve["amount"])),
                    delegate=None if info.get("delegate") is None else str(info["delegate"]),
                    close_authority=(
                        None if info.get("closeAuthority") is None else str(info["closeAuthority"])
                    ),
                    state=str(info.get("state", "")),
                    kind=str(parsed["type"]),
                    extensions=tuple(str(e["extension"]) for e in info.get("extensions", ())),
                    space=int(account["space"] if "space" in account else account["data"]["space"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"unparsable_token_account:{type(exc).__name__}") from exc
        if rows[-1].program != program:
            raise ValueError(f"program_mismatch:{rows[-1].address[:8]}")
    return tuple(rows)


def list_token_accounts(rpc: Rpc, wallet: str) -> tuple[TokenAccountRow, ...]:
    rows: list[TokenAccountRow] = []
    for program in (TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID):
        result = rpc.call(
            "getTokenAccountsByOwner",
            [wallet, {"programId": program}, {"encoding": "jsonParsed", "commitment": "confirmed"}],
        )
        rows.extend(parse_token_accounts(result["value"], program=program))
    return tuple(rows)


def classify(row: TokenAccountRow, *, wallet: str, token_2022: bool = False) -> str:
    """The verdict of one listed account. ``token_2022=False`` (the default,
    and the CLI without ``--token-2022``) is the T4.77 behaviour: every
    Token-2022 account is ``skipped:token_2022``."""
    if row.kind != "account":
        return f"skipped:not_token_account:{row.kind}"
    if row.program == TOKEN_2022_PROGRAM_ID and not token_2022:
        return "skipped:token_2022"
    if row.program not in ALLOWED_TOKEN_PROGRAMS:
        return "skipped:token_2022"
    for extension in row.extensions:
        if extension not in ALLOWED_EXTENSIONS_2022:
            return f"skipped:token_2022_extension:{extension}"
    if row.space != expected_space(row.extensions):
        return f"skipped:space_mismatch:{row.space}"
    if row.owner != wallet:
        return "skipped:authority_mismatch"
    if row.delegate is not None:
        return "skipped:authority_mismatch"
    if row.close_authority is not None and row.close_authority != wallet:
        return "skipped:authority_mismatch"
    if row.state != "initialized":
        return "skipped:frozen"
    if row.address != associated_token_address(wallet, row.mint, token_program=row.program):
        return "skipped:not_ata"
    if row.is_native:
        reserve = row.rent_exempt_reserve
        if reserve is None or row.lamports > reserve or row.amount != 0:
            return "skipped:wsol_holds_lamports"
    if row.amount != 0:
        return "skipped:nonzero_balance"
    if row.lamports <= 0:
        return "skipped:no_rent"
    return "close"


def expected_space(extensions: Sequence[str]) -> int:
    """The exact data length a token account with these (allowed) extensions
    has: 165 bare; 165 + 1 AccountType byte + Σ(4 + payload) otherwise."""
    if not extensions:
        return BASE_ACCOUNT_LEN
    payload = sum(_TLV_HEADER_LEN + _EXTENSION_SIZE[name] for name in extensions)
    return BASE_ACCOUNT_LEN + _ACCOUNT_TYPE_LEN + payload


def build_plan(
    rows: Sequence[TokenAccountRow],
    *,
    wallet: str,
    limit: int | None,
    token_2022: bool = False,
    proof_run: bool = False,
) -> Plan:
    """``proof_run`` (the first ``--token-2022`` run): classic ``close``
    verdicts are deferred by name and the selection is capped at **one**
    Token-2022 account, whatever ``limit`` says."""
    if proof_run and not token_2022:
        raise ValueError("proof_run_requires_token_2022")
    judged: list[tuple[TokenAccountRow, str]] = []
    for row in rows:
        verdict = classify(row, wallet=wallet, token_2022=token_2022)
        if proof_run and verdict == "close" and row.program != TOKEN_2022_PROGRAM_ID:
            verdict = "skipped:proof_run_token_2022_only"
        judged.append((row, verdict))
    selected = [row for row, verdict in judged if verdict == "close"]
    if proof_run:
        limit = 1 if limit is None else min(limit, 1)
    if limit is not None:
        selected = selected[: max(0, limit)]
    return Plan(wallet=wallet, rows=tuple(judged), selected=tuple(selected))


def batches(plan: Plan, *, size: int = BATCH_SIZE) -> tuple[tuple[TokenAccountRow, ...], ...]:
    """Batches never mix programs: classic first, then Token-2022, each cut
    into runs of at most ``size`` — a message with two token programs in it
    is refused by the verifier anyway (``batch_programs_mixed``)."""
    parts: list[tuple[TokenAccountRow, ...]] = []
    for program in (TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID):
        rows = tuple(row for row in plan.selected if row.program == program)
        parts.extend(rows[i : i + size] for i in range(0, len(rows), size))
    return tuple(parts)


def format_table(plan: Plan) -> str:
    lines = [f"{'mint8':<9} {'ata8':<9} {'rent_lamports':>13}  {'program':<10}  verdict"]
    for row, verdict in plan.rows:
        program = _PROGRAM_LABEL.get(row.program, row.program[:8])
        lines.append(
            f"{row.mint[:8]:<9} {row.address[:8]:<9} {row.lamports:>13}  {program:<10}  {verdict}"
        )
    total = plan.total_recoverable
    skipped = ",".join(f"{k}={v}" for k, v in plan.skipped.items()) or "-"
    lines.append(
        f"listed={len(plan.rows)} selected={len(plan.selected)} skipped={skipped} "
        f"total_recoverable_lamports={total} "
        f"total_recoverable_sol={Decimal(total) / LAMPORTS:.9f}"
    )
    parked = sum(row.lamports for row, verdict in plan.rows if verdict == "skipped:token_2022")
    if parked:
        # Named so the operator sees what this script does NOT touch (R64's
        # 34 pump.fun ATAs are Token-2022; closing them is a separate decision).
        lines.append(
            f"token_2022_rent_not_touched_lamports={parked} "
            f"token_2022_rent_not_touched_sol={Decimal(parked) / LAMPORTS:.9f}"
        )
    return "\n".join(lines)


def build_batch_message(
    *,
    wallet: str,
    accounts: Sequence[str],
    blockhash: str,
    priority_fee_lamports: int,
    token_program: str,
) -> Message:
    """``[cu limit, cu price, CloseAccount × n]`` on **one** token program —
    every close refunds to the wallet with the wallet as authority. The unit
    price is floored so the priority fee never exceeds what was asked."""
    n = len(accounts)
    if not 0 < n <= BATCH_SIZE:
        raise ValueError(f"batch_size_out_of_range:{n}")
    if priority_fee_lamports < 0:
        raise ValueError("priority_fee_negative")
    if token_program not in ALLOWED_TOKEN_PROGRAMS:
        raise ValueError(f"token_program_not_allowed:{token_program[:8]}")
    limit = CU_BASE + CU_PER_CLOSE * n
    price = priority_fee_lamports * 1_000_000 // limit
    instructions: list[Instruction] = [set_compute_unit_limit(limit), set_compute_unit_price(price)]
    for account in accounts:
        instructions.append(
            Instruction(
                token_program,
                (
                    AccountMeta(account, False, True),
                    AccountMeta(wallet, False, True),
                    AccountMeta(wallet, True, False),
                ),
                CLOSE_ACCOUNT_DISCRIMINATOR,
            )
        )
    return compile_message(wallet, instructions, blockhash)
