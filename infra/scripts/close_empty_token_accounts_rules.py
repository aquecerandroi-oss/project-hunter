"""The policy half of ``close_empty_token_accounts.py`` (28/09/2026): what this
tool adds on top of the T4.77 close pipeline (``meme_close_atas_plan`` /
``_verify`` / ``_send``), which it reuses and never re-implements.

Every account first gets the T4.77/T4.77b verdict (``classify`` with
``token_2022=True``: token **account**, owner/authority = wallet, no
delegate, not frozen, ``amount == 0`` in atoms, the ATA derived with its own
program, Token-2022 extensions ⊆ ``{immutableOwner}`` with the exact
``space`` — a ``transferFeeAmount`` (withheld fees), confidential transfer,
transfer hook… is ``skipped:token_2022_extension:<name>``). Only a ``close``
verdict is then narrowed by policy, so a chain fact (frozen, balance) is
never relabelled:

- ``skipped:kept_quote_mint:wsol`` / ``:usdc`` — the executor's own quote
  mints (``wallet_holdings.QUOTE_MINTS``). The WSOL ATA is the one Jupiter and
  PumpSwap wrap into during a swap, and the USDC ATA is where the treasury
  (§16) receives: closing either only moves its rent to the next swap or
  inflow that has to recreate it — and a swap already built against it
  would fail. Kept, named.
- ``skipped:recognized_mint`` — a mint of an open position, an in-flight
  buy, or one closed/confirmed within ``RECOGNIZED_GRACE_S`` (60 s) of the
  chain read: ``wallet_holdings.recognized_mints``, the executor's own SQL.

Batches are the verifier's cap (``MAX_CLOSES_PER_BATCH`` = 8
``CloseAccount``): a signed legacy transaction of 8 closes on one program
measures 530 bytes (5 closes: 413) against Solana's 1 232-byte packet
(``TX_SIZE_LIMIT``; a test pins it). The size is not the binding limit;
the verifier's cap is.

No network here. The only I/O is the two reads and the one write, each
taking the session as an argument.
"""

from __future__ import annotations

import getpass
import json
import socket
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Protocol

import obsidian_note_gate
from meme_close_atas_plan import (
    BATCH_SIZE,
    Plan,
    TokenAccountRow,
    batches,
    build_plan,
    list_token_accounts,
)
from meme_close_atas_send import BASE_FEE_LAMPORTS
from obsidian_note_gate import NoteProof, provenance_data
from sqlalchemy import text

from hunter_core.domain.types import uuid7
from hunter_exchanges.jupiter import WRAPPED_SOL_MINT
from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID
from hunter_meme_executor.treasury_rules import USDC_MINT
from hunter_meme_executor.wallet_holdings import recognized_mints

# fmt: off
__all__ = [
    "ACTION_BATCH", "ACTION_INTENT", "ACTION_RUN", "BATCH_SIZE", "IN_FLIGHT_SQL", "IN_FLIGHT_STATUSES",
    "KEPT_QUOTE_MINTS", "NEVER_TOUCH_MINTS", "NOTE_TARGET", "TX_SIZE_LIMIT", "Refused", "batches",
    "OPEN_POSITIONS_SQL", "estimated_fee_lamports", "format_report", "in_flight_buys", "judge",
    "list_accounts", "open_positions", "wallet_balance",
    "read_recognized",
    "refresh_batch", "require_note", "write_audit",
]
# fmt: on

SCRIPT = "infra/scripts/close_empty_token_accounts.py"
NOTE_TARGET: Final = "close_empty_token_accounts"
ACTION_INTENT: Final = "wallet.close_empty_token_accounts.intent"
"""Committed **before** each batch is handed to the signer/broadcast (Astra,
design review): run id, batch, accounts and the note's hashes survive a
process killed mid-send. The batch's ``system_events`` rows (T4.77) carry
the same run id in their ``reason``, and the signature."""
ACTION_BATCH: Final = "wallet.close_empty_token_accounts.batch"
ACTION_RUN: Final = "wallet.close_empty_token_accounts.run"
TX_SIZE_LIMIT: Final = 1_232  # Solana packet data size, bytes
LAMPORTS: Final = Decimal(1_000_000_000)
KEPT_QUOTE_MINTS: Final[Mapping[str, str]] = {WRAPPED_SOL_MINT: "wsol", USDC_MINT: "usdc"}
NEVER_TOUCH_MINTS: Final[Mapping[str, str]] = {
    "DgY9Z8xPG1346Ydrq98ASAZcVdyrurT4tCQ7TDapHcJg": "phishing",
}
"""Mints this tool never builds an instruction for, whatever their account
reads like (security review, 28/09). Freeze state and balance belong to the
issuer: unfrozen and burned to zero by a permanent delegate (a **mint**
extension, invisible on the account), the phishing ATA would pass every
T4.77b check. Checked in ``judge`` before any other verdict and again in
``refresh_batch``. Decision: ``2026-09-28-excecao-auditada-token-golpe``."""
IN_FLIGHT_STATUSES: Final = ("admitted", "simulated", "submitted_unconfirmed")
"""The executor's in-flight buy statuses (``wallet_holdings._RECOGNIZED``,
``repo._PENDING``, ``spot_repo._PENDING``); a test pins them together."""
IN_FLIGHT_SQL: Final = text(
    "SELECT (SELECT count(*) FROM meme_live_orders WHERE side = 'buy' "
    "  AND status IN ('admitted', 'simulated', 'submitted_unconfirmed')) AS meme, "
    "(SELECT count(*) FROM spot_orders WHERE side = 'buy' "
    "  AND status IN ('admitted', 'simulated', 'submitted_unconfirmed')) AS spot"
)
OPEN_POSITIONS_SQL: Final = text(
    "SELECT (SELECT count(*) FROM meme_live_positions WHERE status = 'open') AS meme, "
    "(SELECT count(*) FROM spot_positions WHERE status = 'open') AS spot"
)
"""Shown by the dry run (runbook step 2); their mints are already kept by the
recognized set, so an open position does not refuse the run."""
_AUDIT = text(
    "INSERT INTO audit_logs (id, created_at, organization_id, actor_type, actor_id, action, "
    "  entity_type, entity_id, before, after, metadata) "
    "VALUES (:id, now(), NULL, 'system', NULL, :action, 'wallet', NULL, NULL, "
    "  CAST(:after AS jsonb), CAST(:metadata AS jsonb))"
)
"""System scope (``organization_id IS NULL``, policy ``audit_system_scope``):
the wallet is the desk's, not a tenant's. ``actor_id`` is a UUID column; the
operator's ``--actor`` is recorded unverified in ``metadata.actor_input``, as
``link_portfolio_risk_profile.py`` does."""


class Refused(Exception):
    """A named refusal; nothing has been signed when it is raised."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Session(Protocol):
    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...
    async def commit(self) -> None: ...


class _StrictListing:
    """Astra (design review): ``parse_token_accounts`` iterates whatever
    ``value`` is, so ``{"value": {}}`` from one program read as "no accounts"
    — a partial inventory. Anything but a list is refused here."""

    def __init__(self, rpc: Any) -> None:
        self._rpc = rpc

    def call(self, method: str, params: list[Any]) -> Any:
        result = self._rpc.call(method, params)
        if not isinstance(result, dict) or not isinstance(result.get("value"), list):  # pyright: ignore[reportUnknownMemberType]
            raise ValueError(f"envelope_not_a_list:{method}")
        return result  # pyright: ignore[reportUnknownVariableType]


def list_accounts(rpc: Any, wallet: str) -> tuple[TokenAccountRow, ...]:
    """Both programs, envelope checked; any failure is ``chain_read_failed``."""
    try:
        return list_token_accounts(_StrictListing(rpc), wallet)
    except Exception as exc:
        raise Refused(f"chain_read_failed:{type(exc).__name__}:{str(exc)[:80]}") from exc


def judge(rows: Sequence[TokenAccountRow], *, wallet: str, recognized: frozenset[str]) -> Plan:
    """``NEVER_TOUCH_MINTS`` first, whatever the chain says; then the T4.77b
    verdicts, then policy on the ``close`` ones only."""
    base = build_plan(rows, wallet=wallet, limit=None, token_2022=True)
    judged: list[tuple[TokenAccountRow, str]] = []
    for row, verdict in base.rows:
        if row.mint in NEVER_TOUCH_MINTS:
            verdict = f"skipped:never_touch:{NEVER_TOUCH_MINTS[row.mint]}"
        elif verdict == "close" and row.mint in KEPT_QUOTE_MINTS:
            verdict = f"skipped:kept_quote_mint:{KEPT_QUOTE_MINTS[row.mint]}"
        elif verdict == "close" and row.mint in recognized:
            verdict = "skipped:recognized_mint"
        judged.append((row, verdict))
    selected = tuple(row for row, verdict in judged if verdict == "close")
    return replace(base, rows=tuple(judged), selected=selected)


def refresh_batch(
    batch: Sequence[TokenAccountRow], fresh: Plan
) -> tuple[tuple[TokenAccountRow, ...], tuple[tuple[TokenAccountRow, str], ...]]:
    """TOCTOU: keep a planned row only if the re-read shows every parsed
    ``TokenAccountRow`` field identical (lamports and space included — not the
    raw account bytes, not the slot) and still ``close``. A never-touch mint is
    dropped here again, independently of ``judge``."""
    current = {row.address: (row, verdict) for row, verdict in fresh.rows}
    kept: list[TokenAccountRow] = []
    dropped: list[tuple[TokenAccountRow, str]] = []
    for row in batch:
        seen = current.get(row.address)
        if row.mint in NEVER_TOUCH_MINTS:
            dropped.append((row, f"dropped:never_touch:{NEVER_TOUCH_MINTS[row.mint]}"))
        elif seen is None:
            dropped.append((row, "dropped:account_gone"))
        elif seen[0] != row:
            dropped.append((row, "dropped:account_changed"))
        elif seen[1] != "close":
            dropped.append((row, f"dropped:{seen[1]}"))
        else:
            kept.append(row)
    return tuple(kept), tuple(dropped)


def estimated_fee_lamports(*, n_batches: int, priority_fee_lamports: int) -> int:
    """Upper bound: one signature per batch plus the priority fee asked
    (``build_batch_message`` floors the unit price, never above it)."""
    return n_batches * (BASE_FEE_LAMPORTS + priority_fee_lamports)


def _sol(lamports: int) -> str:
    return f"{Decimal(lamports) / LAMPORTS:.9f}"


def format_report(plan: Plan, *, priority_fee_lamports: int, max_batches: int | None) -> str:
    lines = [f"{'address':<44}  {'program':<10}  {'mint':<44}  {'lamports':>9}  verdict"]
    for row, verdict in plan.rows:
        program = "token" if row.program == TOKEN_PROGRAM_ID else "token-2022"
        lines.append(
            f"{row.address:<44}  {program:<10}  {row.mint:<44}  {row.lamports:>9}  {verdict}"
        )
    parts = batches(plan)
    run = parts if max_batches is None else parts[:max_batches]
    this_run = sum(r.lamports for part in run for r in part)
    fee = estimated_fee_lamports(n_batches=len(run), priority_fee_lamports=priority_fee_lamports)
    skipped = ",".join(f"{k}={v}" for k, v in plan.skipped.items()) or "-"
    lines += [
        f"listed={len(plan.rows)} selected={len(plan.selected)} skipped={skipped}",
        f"total_recoverable_lamports={plan.total_recoverable} "
        f"total_recoverable_sol={_sol(plan.total_recoverable)}",
        f"batches={len(parts)} batch_size={BATCH_SIZE} this_run_batches={len(run)} "
        f"this_run_lamports={this_run}",
        f"estimated_fee_lamports={fee} expected_net_lamports={this_run - fee} "
        f"expected_net_sol={_sol(this_run - fee)}",
    ]
    if any(v.startswith("skipped:kept_quote_mint") for _, v in plan.rows):
        lines.append(
            "kept_quote_mint: WSOL/USDC ATAs stay open (swaps wrap into WSOL; the treasury "
            "receives USDC) — closing them only moves the rent to the next swap/inflow"
        )
    return "\n".join(lines)


async def read_recognized(session: Any, *, since: datetime) -> frozenset[str]:
    """The executor's own recognized set (open, in flight, closed ≤ 60 s)."""
    return await recognized_mints(session, since=since)


async def _counts(session: Any, statement: Any) -> dict[str, int]:
    row = (await session.execute(statement)).mappings().one()
    return {"meme": int(row["meme"]), "spot": int(row["spot"])}


async def in_flight_buys(session: Any) -> dict[str, int]:
    return await _counts(session, IN_FLIGHT_SQL)


async def open_positions(session: Any) -> dict[str, int]:
    return await _counts(session, OPEN_POSITIONS_SQL)


def wallet_balance(rpc: Any, wallet: str) -> int:
    """Lamports at ``confirmed`` — a human cross-check for runbook step 4; the
    recovered amount the tool reports comes from each transaction's meta."""
    value = rpc.call("getBalance", [wallet, {"commitment": "confirmed"}])["value"]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("balance_not_an_int")
    return value


def require_note(note: str | None, *, wallet: str, repo_root: Path | None = None) -> NoteProof:
    """``--note``: a Markdown note under ``obsidian/`` naming this tool or the wallet."""
    try:
        return obsidian_note_gate.gate(
            note,
            [[NOTE_TARGET, wallet]],
            repo_root=repo_root or obsidian_note_gate.default_repo_root(),
        )
    except obsidian_note_gate.NoteRefused as refused:
        raise Refused(f"{refused.reason}:{str(refused).split(': ', 1)[1]}") from refused


async def write_audit(
    session: Session,
    *,
    action: str,
    after: Mapping[str, Any],
    actor: str,
    reason: str,
    proof: NoteProof | None,
) -> None:
    """One ``audit_logs`` row, committed on its own (commit-as-you-go)."""
    metadata: dict[str, Any] = {
        "script": SCRIPT,
        "actor_input": actor,
        "reason": reason,
        "hostname": socket.gethostname(),
        "os_user": getpass.getuser(),
        **(provenance_data(proof) if proof is not None else {"note": None}),
    }
    await session.execute(
        _AUDIT,
        {
            "id": uuid7(),
            "action": action,
            "after": json.dumps(dict(after)),
            "metadata": json.dumps(metadata),
        },
    )
    await session.commit()
