#!/usr/bin/env python3
"""Audited correction of the ``spot/1`` ATA-rent bug (KB-0171, 01/10/2026): the
executor subtracted a constant 2 039 280 lamports of rent from a buy that
opened its token ATA, while the network charged 1 488 440 — ``sol_spent``
550 840 lamports short, ``pnl_sol``/``r_multiple`` as much too high on the
positions that created an ATA. This recomputes them **from their own entry
transaction** (read-only ``getTransaction``), never from a constant.

    python infra/scripts/spot_fix_ata_rent.py                       # dry run
    python infra/scripts/spot_fix_ata_rent.py --apply --note obsidian/11-KNOWLEDGE/KB-0171-custo-real-da-spot-1.md

On the VPS: ``bash infra/vps/compose.sh ops python infra/scripts/spot_fix_ata_rent.py ...``
(runbook in ``docs/RISK_ENGINE_MEME.md`` §19).

Candidates: ``spot_positions`` with ``ata_rent_lamports > 0`` or an
``entry.sol_spent_source`` that folded the rent. Per closed candidate: the
entry order's signature and admitted wallet → the meta read by the executor's
own ``fill_from_transaction`` → its SOL and token deltas must equal what the
position recorded (``entry.sol_delta_lamports``, ``entry.filled_atoms`` — the
``tokens`` column is 0 after a close) → the rent this transaction added to the
wallet's ATA → ``entry_spend`` (the executor's rule) → ``pnl = received −
spent``, ``R = pnl ÷ initial_risk_sol`` (the original R unit). Open candidates
are listed and skipped (the executor owns them).

**Dry run by default**: prints before/after and the Σ the refutation reads,
writes nothing. ``--apply`` needs ``--note`` (a Markdown note under
``obsidian/`` that mentions every corrected position — full id or its first 8
characters; the T4.93 gate) and writes, **in one transaction**, each UPDATE
(guarded by the exact accounting it read, rows locked ``FOR UPDATE``) and one
``audit_logs`` row per position (system scope). Any refusal — including a rent
that cannot be read from the chain — writes nothing at all. A second run finds
every row already correct and writes nothing. ``spot_orders.fill`` is left as
the executor recorded it (the audit row carries the before/after).

Connects with ``DATABASE_URL_MIGRATIONS``; RPC = ``--rpc`` or
``SOLANA_RPC_URL`` or the public mainnet endpoint (read-only client, never
printed). Exit codes: 0 done (or a clean dry run), 2 usage, 65 refused.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import socket
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Protocol

import obsidian_note_gate
from meme_ops_db import migration_url
from spot_fix_ata_rent_rules import Fix, Refused, plan_fix
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from hunter_core.domain.types import uuid7

__all__ = ["Fix", "Refused", "main", "plan_fix", "run"]

EX_REFUSED = 65
SCRIPT: Final = "infra/scripts/spot_fix_ata_rent.py"
ACTION: Final = "spot.position.ata_rent_corrected"
_CANDIDATES = text(
    "SELECT p.id, p.status, p.mint, p.market_symbol, p.entry, p.params, p.sol_spent_lamports, "
    "  p.ata_rent_lamports, p.sol_received_lamports, p.pnl_sol, p.r_multiple, "
    "  p.initial_risk_sol, o.tx_signature, o.fill AS entry_fill, "
    "  o.admission->>'wallet_id' AS wallet "
    "FROM spot_positions p JOIN spot_orders o ON o.id = p.entry_order_id "
    "WHERE p.status = 'closed' AND (p.ata_rent_lamports > 0 OR p.entry->>'sol_spent_source' IN "
    "  ('signature_delta_rent_folded', 'signature_delta_rent_unknown')) "
    "ORDER BY p.entry_at FOR UPDATE OF p"
)
"""Only **closed** rows are locked (guardian F1): an open one is the executor's,
marked and sold every tick — never held while the chain is read."""
_OPEN_CANDIDATES = text(
    "SELECT p.id, p.market_symbol FROM spot_positions p WHERE p.status <> 'closed' "
    "  AND (p.ata_rent_lamports > 0 OR p.entry->>'sol_spent_source' IN "
    "  ('signature_delta_rent_folded', 'signature_delta_rent_unknown')) ORDER BY p.entry_at"
)
_UPDATE = text(
    "UPDATE spot_positions SET sol_spent_lamports = :spent, ata_rent_lamports = :rent, "
    "  pnl_sol = :pnl, r_multiple = :r, entry = entry || CAST(:entry_patch AS jsonb), "
    "  params = params || CAST(:params_patch AS jsonb), updated_at = now() "
    "WHERE id = CAST(:id AS uuid) AND status = 'closed' AND sol_spent_lamports = :old_spent "
    "  AND ata_rent_lamports = :old_rent AND pnl_sol = :old_pnl AND r_multiple = :old_r "
    "RETURNING id"
)
_AUDIT = text(
    "INSERT INTO audit_logs (id, created_at, organization_id, actor_type, actor_id, action, "
    "  entity_type, entity_id, before, after, metadata) "
    "VALUES (:id, now(), NULL, 'system', NULL, :action, 'spot_position', CAST(:entity AS uuid), "
    "  CAST(:before AS jsonb), CAST(:after AS jsonb), CAST(:metadata AS jsonb))"
)
"""System scope (policy ``audit_system_scope``): the desk wallet is no tenant's."""


class TxReader(Protocol):
    def get_transaction(
        self, signature: str, *, commitment: str = "confirmed"
    ) -> dict[str, Any] | None: ...


def _json(values: Mapping[str, Any]) -> str:
    return json.dumps(dict(values), default=str)


async def _write(
    session: AsyncSession, fix: Fix, proof: obsidian_note_gate.NoteProof, actor: str
) -> None:
    b, a, now = fix.before, fix.after, datetime.now(UTC).isoformat()
    correction = {"by": SCRIPT, "at": now, "signature": fix.signature, "note": proof.path,
                  "before": b}  # fmt: skip
    entry_patch = {k: a[k] for k in ("sol_spent_lamports", "ata_rent_lamports", "sol_spent_source")}
    params_patch = {"ata_rent_lamports": a["ata_rent_lamports"],
                    "entry_sol_per_atom": str(fix.entry_sol_per_atom)}  # fmt: skip
    updated = (
        await session.execute(
            _UPDATE,
            {
                "id": fix.position_id,
                "spent": a["sol_spent_lamports"],
                "rent": a["ata_rent_lamports"],
                "pnl": a["pnl_sol"],
                "r": a["r_multiple"],
                "entry_patch": _json({**entry_patch, "rent_correction": correction}),
                "params_patch": _json(params_patch),
                "old_spent": b["sol_spent_lamports"],
                "old_rent": b["ata_rent_lamports"],
                "old_pnl": b["pnl_sol"],
                "old_r": b["r_multiple"],
            },  # fmt: skip
        )
    ).all()
    if len(updated) != 1:
        raise Refused("position_moved", f"{fix.position_id}: the row changed under the lock")
    meta = {"script": SCRIPT, "hostname": socket.gethostname(), "os_user": getpass.getuser(),
            "actor_input": actor, "signature": fix.signature, "rent_source": "tx_meta_ata_balance",
            "bug": "KB-0171", **obsidian_note_gate.provenance_data(proof)}  # fmt: skip
    await session.execute(
        _AUDIT,
        {
            "id": uuid7(),
            "action": ACTION,
            "entity": fix.position_id,
            "before": _json(b),
            "after": _json(a),
            "metadata": _json(meta),
        },  # fmt: skip
    )


async def run(
    session: AsyncSession,
    rpc: TxReader,
    *,
    apply: bool,
    note: str | None,
    actor: str,
    repo_root: Path | None = None,
) -> str:
    """The report; ``Refused`` before any write (the caller's transaction rolls back)."""
    lines = [
        f"{r['id']} {r['market_symbol']} [open: skipped, rerun after close]"
        for r in (await session.execute(_OPEN_CANDIDATES)).mappings().all()
    ]
    rows = (await session.execute(_CANDIDATES)).mappings().all()
    fixes: list[Fix] = []
    for row in rows:
        signature = row["tx_signature"]
        try:
            tx = None if signature is None else rpc.get_transaction(signature)
        except Exception as exc:  # a named refusal, never a traceback; nothing written
            raise Refused("rpc_failed", f"{row['id']}: {type(exc).__name__}") from exc
        fixes.append(plan_fix(dict(row), tx))
    lines += [fix.describe() for fix in fixes]
    todo = [fix for fix in fixes if fix.changed]
    delta_pnl = sum((f.after["pnl_sol"] - f.before["pnl_sol"] for f in todo), Decimal(0))
    delta_r = sum((f.after["r_multiple"] - f.before["r_multiple"] for f in todo), Decimal(0))
    lines.append(
        f"closed_candidates={len(rows)} to_correct={len(todo)} "
        f"Δ Σ pnl_sol={delta_pnl} Δ Σ r={delta_r:.4f}"
    )
    report = "\n".join(lines)
    if not todo:
        return f"{report}\nnothing to correct: nothing written"
    groups = [[f.position_id, f.position_id[:8]] for f in todo]
    if not apply:
        return f"{report}\ndry-run: nothing written (add --apply); " + (
            obsidian_note_gate.describe_required_note(groups)
        )
    try:
        proof = obsidian_note_gate.gate(
            note, groups, repo_root=repo_root or obsidian_note_gate.default_repo_root()
        )
    except obsidian_note_gate.NoteRefused as refused:
        raise Refused(refused.reason, str(refused).split(": ", 1)[1]) from refused
    for fix in todo:
        await _write(session, fix, proof, actor)
    return f"{report}\napplied: {len(todo)} positions corrected; {len(todo)} audit_logs rows"


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--note", default=None, metavar="PATH", help="--apply only")
    parser.add_argument("--actor", default="Everton")
    parser.add_argument("--rpc", default=None, help="read-only RPC URL (default SOLANA_RPC_URL)")
    return parser.parse_args(argv)


async def _main(argv: Sequence[str]) -> int:
    from hunter_exchanges.pumpfun.tx_rpc import MAINNET_PUBLIC_RPC_URL, SolanaTxRpcClient

    args = parse_args(argv)
    url = args.rpc or os.environ.get("SOLANA_RPC_URL", "").strip() or str(MAINNET_PUBLIC_RPC_URL)
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    rpc = SolanaTxRpcClient(url)  # read-only: allow_send stays off
    try:
        async with AsyncSession(engine) as session, session.begin():  # one transaction
            report = await run(session, rpc, apply=args.apply, note=args.note, actor=args.actor)
    except Refused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return EX_REFUSED
    finally:
        rpc.close()
        await engine.dispose()
    print(report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
