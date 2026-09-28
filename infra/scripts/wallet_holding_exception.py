#!/usr/bin/env python3
"""Audited per-mint exception to §3.2's ``wallet_unrecognized_holdings`` (F1,
decision 2026-09-28, ``obsidian/06-DECISIONS/2026-09-28-excecao-auditada-token-golpe.md``)
— the only sanctioned way to write ``meme_wallet_holding_exceptions``.

    python infra/scripts/wallet_holding_exception.py --list
    python infra/scripts/wallet_holding_exception.py --add --wallet <PUBKEY> \\
        --mint <MINT> --program token-2022 --reason "..." --actor Everton \\
        --note obsidian/06-DECISIONS/<nota>.md [--allow-unfrozen] [--apply]
    python infra/scripts/wallet_holding_exception.py --revoke --wallet <PUBKEY> \\
        --mint <MINT> --reason "..." --actor Everton [--apply]

On the VPS: ``bash infra/vps/compose.sh ops python infra/scripts/wallet_holding_exception.py ...``
(runbook in ``docs/RISK_ENGINE_MEME.md`` §3.2).

**Dry run by default**: prints the plan (chain facts, the row it would write, the
note it needs), writes nothing. ``--apply`` writes the row and one
``audit_logs`` row (system scope, ``organization_id`` NULL, the operator's
``--actor`` in ``metadata.actor_input``) **in one transaction** — either both
land or neither. ``--add`` re-reads the chain first (``SOLANA_RPC_URL`` or the
public mainnet endpoint, read-only client, ``--rpc`` overrides; the URL is never
printed), then the executor's recognized set, then applies the policy of
``wallet_holding_exception_rules.py``; ``--add --apply`` also needs ``--note``,
a Markdown note under ``obsidian/`` that mentions the mint (the T4.93 gate).
``--revoke`` needs no chain and no note (it only tightens). ``--wallet`` is the
public key, given explicitly: this tool never reads a key and never signs.

Refusals, by name and nothing written: every one of the rules module, plus
``exception_already_active``, ``exception_not_found`` and the note gate's
(``note_required``, ``note_outside_obsidian``, ``note_missing``,
``note_not_markdown``, ``note_does_not_mention_target``). Connects with
``DATABASE_URL_MIGRATIONS`` (direct, never the pooler). Exit codes: 0 done (or a
clean dry run), 2 usage (argparse), 65 refused.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import socket
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Protocol

import obsidian_note_gate
from meme_ops_db import migration_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from wallet_holding_exception_rules import (
    Refused,
    judge,
    read_facts,
    require_pubkey,
    require_reason,
)

from hunter_core.domain.types import uuid7
from hunter_exchanges.pumpfun.solana_codec import TOKEN_2022_PROGRAM_ID, TOKEN_PROGRAM_ID
from hunter_meme_executor.wallet_holdings import RECOGNIZED_GRACE_S, recognized_mints

__all__ = ["TABLE", "add", "list_exceptions", "main", "parse_args", "revoke"]

EX_REFUSED = 65
SCRIPT: Final = "infra/scripts/wallet_holding_exception.py"
TABLE: Final = "meme_wallet_holding_exceptions"
ACTION_ADD: Final = "wallet.holding_exception.add"
ACTION_REVOKE: Final = "wallet.holding_exception.revoke"
PROGRAMS: Final = {
    "token-2022": TOKEN_2022_PROGRAM_ID,
    "token": TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID: TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID: TOKEN_PROGRAM_ID,
}
_ALIAS = {TOKEN_2022_PROGRAM_ID: "token-2022", TOKEN_PROGRAM_ID: "token"}
_PARSED = {"encoding": "jsonParsed", "commitment": "confirmed"}

_ACTIVE = text(
    f"SELECT id, revoked_at FROM {TABLE} "  # noqa: S608 - constant name
    "WHERE wallet = :wallet AND mint = :mint AND revoked_at IS NULL FOR UPDATE"
)
_INSERT = text(
    f"INSERT INTO {TABLE} (id, wallet, token_program, mint, max_atoms, decimals, "  # noqa: S608
    "require_frozen, evidence, reason, note_path, note_sha256, created_by) VALUES (:id, :wallet, "
    ":program, :mint, :atoms, :decimals, :require_frozen, CAST(:evidence AS jsonb), :reason, "
    ":note, :sha, :actor)"
)
_REVOKE = text(
    f"UPDATE {TABLE} SET revoked_at = now(), revoked_by = :actor, revoke_reason = :reason "  # noqa: S608
    "WHERE id = :id AND revoked_at IS NULL RETURNING revoked_at"
)
_LIST = text(
    f"SELECT id, wallet, token_program, mint, max_atoms, decimals, require_frozen, created_by, "  # noqa: S608
    f"created_at, revoked_at, revoked_by FROM {TABLE} "
    "WHERE CAST(:wallet AS text) IS NULL OR wallet = :wallet ORDER BY created_at"
)
_AUDIT = text(
    "INSERT INTO audit_logs (id, created_at, organization_id, actor_type, actor_id, action, "
    "  entity_type, entity_id, before, after, metadata) "
    "VALUES (:id, now(), NULL, 'system', NULL, :action, 'wallet_holding_exception', :entity, "
    "  CAST(:before AS jsonb), CAST(:after AS jsonb), CAST(:metadata AS jsonb))"
)
"""System scope (policy ``audit_system_scope``): the desk wallet is no tenant's."""


class Rpc(Protocol):
    def call(self, method: str, params: list[Any]) -> Any: ...


async def _audit(
    session: AsyncSession,
    action: str,
    entity: str,
    *,
    before: dict[str, Any] | None,
    after: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    meta = {"script": SCRIPT, "hostname": socket.gethostname(), "os_user": getpass.getuser()}
    await session.execute(
        _AUDIT,
        {
            "id": uuid7(),
            "action": action,
            "entity": entity,
            "before": None if before is None else json.dumps(before),
            "after": json.dumps(after),
            "metadata": json.dumps({**meta, **metadata}),
        },
    )


async def add(
    session: AsyncSession,
    rpc: Rpc,
    *,
    wallet: str,
    program: str,
    mint: str,
    reason: str | None,
    actor: str,
    note: str | None,
    allow_unfrozen: bool,
    apply: bool,
    repo_root: Path | None = None,
) -> str:
    """Chain first, then the recognized set (the executor's order), then policy."""
    wallet, mint = require_pubkey(wallet, "wallet"), require_pubkey(mint, "mint")
    checked = require_reason(reason)
    observed_at = datetime.now(UTC)
    accounts = rpc.call("getTokenAccountsByOwner", [wallet, {"mint": mint}, _PARSED])
    mint_info = rpc.call("getAccountInfo", [mint, _PARSED])
    facts = read_facts(
        accounts, mint_info, wallet=wallet, program=program, mint=mint, observed_at=observed_at
    )
    since = observed_at - timedelta(seconds=RECOGNIZED_GRACE_S)
    plan = judge(
        facts,
        wallet=wallet,
        recognized=await recognized_mints(session, since=since),
        allow_unfrozen=allow_unfrozen,
    )
    if (await session.execute(_ACTIVE, {"wallet": wallet, "mint": mint})).first() is not None:
        raise Refused("exception_already_active", f"{wallet} already excepts {mint}")
    row: dict[str, Any] = {
        "wallet": wallet,
        "program": program,
        "mint": mint,
        "atoms": plan.max_atoms,
        "decimals": plan.decimals,
        "require_frozen": plan.require_frozen,
        "reason": checked,
        "actor": actor,
    }
    report = "\n".join(
        [
            f"add exception: wallet {wallet} · {_ALIAS[program]} · mint {mint}",
            f"max_atoms={plan.max_atoms} decimals={plan.decimals} "
            f"require_frozen={str(plan.require_frozen).lower()}",
            f"evidence: {json.dumps(plan.evidence, ensure_ascii=False)}",
            f"reason: {checked}",
        ]
    )
    groups = [[mint]]
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
    exception_id = str(uuid7())
    await session.execute(
        _INSERT,
        {
            **row,
            "id": exception_id,
            "evidence": json.dumps(plan.evidence),
            "note": proof.path,
            "sha": proof.sha256,
        },
    )
    after = {k: v for k, v in row.items() if k != "atoms"} | {"max_atoms": str(plan.max_atoms)}
    metadata = {
        "actor_input": actor,
        "reason": checked,
        "evidence": plan.evidence,
        **obsidian_note_gate.provenance_data(proof),
    }
    await _audit(session, ACTION_ADD, exception_id, before=None, after=after, metadata=metadata)
    return f"{report}\napplied: exception {exception_id} written; audit_logs written"


async def revoke(
    session: AsyncSession, *, wallet: str, mint: str, reason: str | None, actor: str, apply: bool
) -> str:
    wallet, mint = require_pubkey(wallet, "wallet"), require_pubkey(mint, "mint")
    checked = require_reason(reason)
    found = (await session.execute(_ACTIVE, {"wallet": wallet, "mint": mint})).first()
    if found is None:
        raise Refused("exception_not_found", f"no active exception of {wallet} for {mint}")
    exception_id = str(found[0])
    report = f"revoke exception {exception_id}: wallet {wallet} · mint {mint}\nreason: {checked}"
    if not apply:
        return f"{report}\ndry-run: nothing written (add --apply)"
    revoked_at = (
        await session.execute(_REVOKE, {"id": exception_id, "actor": actor, "reason": checked})
    ).scalar_one()
    after = {"revoked_at": revoked_at.isoformat(), "revoked_by": actor, "revoke_reason": checked}
    await _audit(
        session,
        ACTION_REVOKE,
        exception_id,
        before={"revoked_at": None},
        after=after,
        metadata={"actor_input": actor, "reason": checked, "wallet": wallet, "mint": mint},
    )
    return f"{report}\napplied: exception revoked; audit_logs written"


async def list_exceptions(session: AsyncSession, *, wallet: str | None = None) -> str:
    rows = (await session.execute(_LIST, {"wallet": wallet})).mappings().all()
    if not rows:
        return "no exceptions"
    lines: list[str] = []
    for r in rows:
        state = (
            "active"
            if r["revoked_at"] is None
            else f"revoked {r['revoked_at'].isoformat()} by {r['revoked_by']}"
        )
        lines.append(
            f"{r['id']}  {r['wallet']}  {_ALIAS.get(r['token_program'], r['token_program'])}  "
            f"{r['mint']}  max_atoms={r['max_atoms']} decimals={r['decimals']} "
            f"require_frozen={str(r['require_frozen']).lower()}  "
            f"by {r['created_by']} at {r['created_at'].isoformat()}  {state}"
        )
    return "\n".join(lines)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    acts = parser.add_mutually_exclusive_group(required=True)
    acts.add_argument("--list", action="store_true")
    acts.add_argument("--add", action="store_true")
    acts.add_argument("--revoke", action="store_true")
    parser.add_argument("--wallet", metavar="PUBKEY", default=None)
    parser.add_argument("--mint", default=None)
    parser.add_argument("--program", default=None, help="token-2022 | token (or the program id)")
    parser.add_argument("--reason", default=None)
    parser.add_argument("--actor", default="Everton")
    parser.add_argument("--note", default=None, metavar="PATH", help="--add --apply only")
    parser.add_argument("--allow-unfrozen", dest="allow_unfrozen", action="store_true")
    parser.add_argument("--rpc", default=None, help="read-only RPC URL (default SOLANA_RPC_URL)")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if (args.add or args.revoke) and (args.wallet is None or args.mint is None):
        parser.error("--add/--revoke need --wallet PUBKEY and --mint MINT")
    if args.add:
        if args.program not in PROGRAMS:
            parser.error("--add needs --program token-2022 | token")
        args.program = PROGRAMS[args.program]
    return args


def _rpc_url(override: str | None) -> str:
    from hunter_exchanges.pumpfun.tx_rpc import MAINNET_PUBLIC_RPC_URL

    return override or os.environ.get("SOLANA_RPC_URL", "").strip() or str(MAINNET_PUBLIC_RPC_URL)


async def _main(argv: Sequence[str]) -> int:
    from hunter_exchanges.pumpfun.tx_rpc import SolanaTxRpcClient

    args = parse_args(argv)
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    rpc = SolanaTxRpcClient(_rpc_url(args.rpc)) if args.add else None  # cannot broadcast
    try:
        async with AsyncSession(engine) as session, session.begin():  # one transaction
            if args.add:
                assert rpc is not None
                report = await add(
                    session, rpc, wallet=args.wallet, program=args.program, mint=args.mint,
                    reason=args.reason, actor=args.actor, note=args.note,
                    allow_unfrozen=args.allow_unfrozen, apply=args.apply,
                )  # fmt: skip
            elif args.revoke:
                report = await revoke(
                    session, wallet=args.wallet, mint=args.mint, reason=args.reason,
                    actor=args.actor, apply=args.apply,
                )  # fmt: skip
            else:
                report = await list_exceptions(session, wallet=args.wallet)
    except Refused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return EX_REFUSED
    finally:
        if rpc is not None:
            rpc.close()
        await engine.dispose()
    print(report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
