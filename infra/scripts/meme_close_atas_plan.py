"""The pure half of ``meme_close_atas.py`` (T4.77): read a wallet's token
accounts (``getTokenAccountsByOwner``, ``jsonParsed``, Token program **and**
Token-2022), give every account a named verdict, select the ones whose rent
can be recovered, cut them into batches and build the message a batch signs.

Verdicts (one per listed account, all printed in the dry-run table):

- ``close`` — Token program, owned by the wallet, ``amount == 0``, not
  frozen, no delegate, close authority absent or the wallet itself, and (for
  the native WSOL account) no lamports beyond the rent-exempt reserve;
- ``skipped:token_2022`` — listed, never closed (extensions such as
  transfer fees or permanent delegates make the classic close unsafe to
  reason about here; the executor's own close only ever met the classic
  program on the curve);
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

from meme_close_atas_verify import MAX_CLOSES_PER_BATCH

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
    "BATCH_SIZE",
    "CU_PER_CLOSE",
    "CU_BASE",
    "Plan",
    "TokenAccountRow",
    "batches",
    "build_batch_message",
    "build_plan",
    "classify",
    "format_table",
    "list_token_accounts",
    "parse_token_accounts",
]

BATCH_SIZE = MAX_CLOSES_PER_BATCH
CU_PER_CLOSE = 5_000  # a CloseAccount costs ~2 900 CU on mainnet; headroom, never tight
CU_BASE = 5_000
LAMPORTS = Decimal(1_000_000_000)


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
            info = account["data"]["parsed"]["info"]
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


def classify(row: TokenAccountRow, *, wallet: str) -> str:
    if row.program != TOKEN_PROGRAM_ID:
        return "skipped:token_2022"
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


def build_plan(rows: Sequence[TokenAccountRow], *, wallet: str, limit: int | None) -> Plan:
    judged = tuple((row, classify(row, wallet=wallet)) for row in rows)
    selected = [row for row, verdict in judged if verdict == "close"]
    if limit is not None:
        selected = selected[: max(0, limit)]
    return Plan(wallet=wallet, rows=judged, selected=tuple(selected))


def batches(plan: Plan, *, size: int = BATCH_SIZE) -> tuple[tuple[TokenAccountRow, ...], ...]:
    rows = plan.selected
    return tuple(rows[i : i + size] for i in range(0, len(rows), size))


def format_table(plan: Plan) -> str:
    lines = [f"{'mint8':<9} {'ata8':<9} {'rent_lamports':>13}  verdict"]
    for row, verdict in plan.rows:
        lines.append(f"{row.mint[:8]:<9} {row.address[:8]:<9} {row.lamports:>13}  {verdict}")
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
    *, wallet: str, accounts: Sequence[str], blockhash: str, priority_fee_lamports: int
) -> Message:
    """``[cu limit, cu price, CloseAccount × n]`` — every close refunds to the
    wallet with the wallet as authority. The unit price is floored so the
    priority fee never exceeds what was asked."""
    n = len(accounts)
    if not 0 < n <= BATCH_SIZE:
        raise ValueError(f"batch_size_out_of_range:{n}")
    if priority_fee_lamports < 0:
        raise ValueError("priority_fee_negative")
    limit = CU_BASE + CU_PER_CLOSE * n
    price = priority_fee_lamports * 1_000_000 // limit
    instructions: list[Instruction] = [set_compute_unit_limit(limit), set_compute_unit_price(price)]
    for account in accounts:
        instructions.append(
            Instruction(
                TOKEN_PROGRAM_ID,
                (
                    AccountMeta(account, False, True),
                    AccountMeta(wallet, False, True),
                    AccountMeta(wallet, True, False),
                ),
                CLOSE_ACCOUNT_DISCRIMINATOR,
            )
        )
    return compile_message(wallet, instructions, blockhash)
