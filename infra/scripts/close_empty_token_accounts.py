#!/usr/bin/env python3
"""Recover the rent of the robot wallet's EMPTY token accounts (28/09/2026)
— dry-run by default; ``--apply`` is Everton's, audited, on the VPS.

    # dry run: every account (address, program, mint, lamports, verdict),
    # totals, fee estimate, in-flight buys; nothing signed, sent or written
    bash infra/vps/compose.sh ops python infra/scripts/close_empty_token_accounts.py \\
        --user ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4

    # apply (signs with the executor's own SOLANA_WALLET_SECRET_KEY, loaded
    # by ``MemeSigner.from_environment`` inside this path only, never printed)
    bash infra/vps/compose.sh ops python infra/scripts/close_empty_token_accounts.py \\
        --user ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4 --apply \\
        --note obsidian/06-DECISIONS/Revisoes-Astra/Fechar-contas-vazias.md

The close itself is the T4.77/T4.77b pipeline, reused, never re-implemented:
``meme_close_atas_plan`` (verdicts, batches of 8 on one program),
``meme_close_atas_send.run_batch`` (build → ``meme_close_atas_verify``: only
ComputeBudget + ``CloseAccount`` with destination = authority = the wallet →
simulate with the balance invariant → sign once → ``system_events`` committed
before the broadcast → confirm → recovered read from the tx meta). This file
adds the policy and the order (``close_empty_token_accounts_rules``):

``--apply``: kill switch read (only ``EMERGENCY``, or an unreadable state,
refuses — rent recovery is not an entry, and is safest with entries off) →
no meme/spot buy in flight → chain read (both programs, envelope checked),
then the executor's recognized set (read time − 60 s) → plan → nothing to
close ⇒ exit 0 → ``--note`` gate → signer loaded, and it must be ``--user``
(the rent destination; refused otherwise) → per batch: kill switch and
in-flight again, the wallet re-read and the batch cut to the rows whose parsed
fields are all unchanged and still ``close`` (TOCTOU), an ``audit_logs``
intent row committed, ``run_batch``, an ``audit_logs`` result row; stop at
the first batch that is not ``confirmed`` or that recovered less than
``Σ rent − fees``. A run row (``finally``, after a rollback) sums it up,
refusals included. ``NEVER_TOUCH_MINTS`` (the 28/09 phishing mint) never
reaches a batch, whatever its account reads like.

Exit codes: 0 done / clean dry-run / nothing to close; 64 usage; 65 refused
by name — **nothing signed in the current batch** (earlier batches of the
run, if any, confirmed cleanly and are printed); 66 sent but not confirmed;
67 failed on chain; 68 a batch was **signed and confirmed**, then the run
stopped (its audit row did not land, or it recovered less than expected).
66, 67 and 68: reconcile the printed signature before running again.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in ("services/meme-executor", "packages/exchange-adapters", "packages/risk-core"):
    candidate = str(REPO_ROOT / extra)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import close_empty_token_accounts_rules as rules  # noqa: E402
from close_empty_token_accounts_reads import (  # noqa: E402
    Deps,
    RunLog,
    SignTracker,
    balance_text,
    db_counts,
    in_flight_counts,
    preflight,
    rollback_quietly,
    snapshot,
)
from meme_close_atas import EX_FAILED, EX_REFUSED, EX_UNCONFIRMED, EX_USAGE  # noqa: E402
from meme_close_atas_plan import Plan  # noqa: E402
from meme_close_atas_send import BASE_FEE_LAMPORTS, BatchResult, result_json  # noqa: E402
from meme_close_atas_verify import MAX_PRIORITY_FEE_LAMPORTS  # noqa: E402
from meme_ops_db import migration_url  # noqa: E402
from obsidian_note_gate import describe_required_note  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from hunter_core.domain.types import uuid7  # noqa: E402
from hunter_core.execution.meme.signer import MemeSigner  # noqa: E402
from hunter_core.redis import create_redis  # noqa: E402
from hunter_core.settings import Settings  # noqa: E402
from hunter_exchanges.pumpfun.tx_rpc import MAINNET_PUBLIC_RPC_URL, SolanaTxRpcClient  # noqa: E402

# fmt: off
__all__ = [
    "EX_FAILED", "EX_REFUSED", "EX_STOPPED_AFTER_CONFIRMED", "EX_UNCONFIRMED", "EX_USAGE", "Deps",
    "apply_with", "dry_run_with", "main", "parse_args", "rpc_client",
]
# fmt: on

EX_STOPPED_AFTER_CONFIRMED = 68  # signed AND confirmed, then stopped — never 65 (module doc)

_PUBKEY = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--user", default=None, help="the wallet public key (both modes)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--note", default=None, help="obsidian/...md naming the tool or wallet")
    parser.add_argument("--max-batches", type=int, default=None, help="default: all")
    parser.add_argument("--priority-fee-lamports", type=int, default=10_000)
    parser.add_argument("--actor", default="everton", help="who runs it (audit_logs)")
    parser.add_argument("--reason", default="recuperar aluguel de contas de token vazias")
    parser.add_argument("--rpc", default=MAINNET_PUBLIC_RPC_URL)
    return parser.parse_args(argv)


def usage_error(args: argparse.Namespace) -> str | None:
    if not args.user or not _PUBKEY.match(args.user):
        return "--user <wallet public key, base58> is required"
    if args.max_batches is not None and args.max_batches < 1:
        return "--max-batches must be >= 1"
    if not 0 <= args.priority_fee_lamports <= MAX_PRIORITY_FEE_LAMPORTS:
        return f"--priority-fee-lamports must be in 0..{MAX_PRIORITY_FEE_LAMPORTS}"
    if not str(args.actor).strip():
        return "--actor must not be empty"
    return None


def _report(plan: Plan, args: argparse.Namespace) -> None:
    fee = args.priority_fee_lamports
    print(rules.format_report(plan, priority_fee_lamports=fee, max_batches=args.max_batches))


async def dry_run_with(args: argparse.Namespace, *, session: Any, rpc: Any, deps: Deps) -> int:
    plan = await snapshot(session, rpc, args.user, deps)
    _report(plan, args)
    counts = await in_flight_counts(session, deps)
    busy = " (--apply would refuse)" if sum(counts.values()) else ""
    print(f"in_flight_buys meme={counts['meme']} spot={counts['spot']}{busy}")
    held = await db_counts(session, deps.open_positions)
    print(f"open_positions meme={held['meme']} spot={held['spot']} (their mints are kept)")
    balance, readable = balance_text(rpc, args.user, deps)
    print(balance)
    print(describe_required_note([[rules.NOTE_TARGET, args.user]]))
    print("dry-run: nothing signed, nothing sent, nothing written (add --apply --note ...)")
    if not readable:  # runbook step 4 compares this number: said, and not a success
        print("refused: balance_unreadable (run the dry run again)", file=sys.stderr)
        return EX_REFUSED
    return 0


async def _audit(
    session: Any, args: argparse.Namespace, run: RunLog, action: str, after: dict[str, Any]
) -> None:
    payload = {"run_id": run.run_id, "wallet": run.wallet, **after}
    await rules.write_audit(
        session, action=action, after=payload, actor=args.actor, reason=args.reason, proof=run.proof
    )


def _batch_code(result: BatchResult) -> int:
    return {"submitted": EX_UNCONFIRMED, "failed": EX_FAILED}.get(result.status, EX_REFUSED)


async def _apply(
    args: argparse.Namespace, session: Any, redis: Any, rpc: Any, deps: Deps, run: RunLog
) -> int:
    wallet = args.user
    run.kill_switch_state = (await preflight(session, redis, deps)).value
    plan = await snapshot(session, rpc, wallet, deps)
    _report(plan, args)
    parts = rules.batches(plan)[: args.max_batches]
    if not parts:
        run.outcome = "nothing_to_close"
        print("nothing to close")
        return 0
    run.proof = rules.require_note(args.note, wallet=wallet, repo_root=deps.repo_root)
    signer = deps.load_signer()
    if signer.pubkey != wallet:  # the rent destination and authority, never another address
        raise rules.Refused(f"destination_not_wallet:signer={signer.pubkey[:8]}")
    fee_allowance = BASE_FEE_LAMPORTS + args.priority_fee_lamports
    for index, planned in enumerate(parts):
        await preflight(session, redis, deps)
        kept, dropped = rules.refresh_batch(planned, await snapshot(session, rpc, wallet, deps))
        for row, why in dropped:
            print(f"{why} {row.address} {row.mint}")
        if not kept:
            run.batches.append({"batch": index, "status": "skipped_all_dropped"})
            continue
        accounts = [row.address for row in kept]
        await _audit(
            session,
            args,
            run,
            rules.ACTION_INTENT,
            {
                "batch": index,
                "accounts": accounts,
                "mints": [row.mint for row in kept],
                "token_program": kept[0].program,
                "expected_rent_lamports": sum(r.lamports for r in kept),
                "dropped": [{"account": row.address, "why": why} for row, why in dropped],
            },
        )
        tracker = SignTracker(signer)
        try:
            result = await deps.run_batch(
                session,
                rpc,
                tracker,
                batch=kept,
                reason=f"{args.reason} [run {run.run_id}]",
                actor=args.actor,
                priority_fee_lamports=args.priority_fee_lamports,
            )
        except BaseException as exc:
            if tracker.signed:  # it may have been broadcast: the crash path names it
                run.batch_in_progress = index
            if tracker.signed or not isinstance(exc, Exception):
                raise
            raise rules.Refused(f"batch_unsent:{type(exc).__name__}") from exc
        print(result_json(result, batch_index=index), flush=True)
        entry = {
            "batch": index,
            "status": result.status,
            "signature": result.signature,
            "accounts": accounts,
            "expected_rent_lamports": result.expected_rent,
            "lamports_recovered": result.lamports_recovered,
            "refusal": result.reason,
        }
        run.batches.append(entry)
        try:
            await _audit(session, args, run, rules.ACTION_BATCH, entry)
        except Exception as exc:  # never turns "maybe sent" into "not sent"
            print(
                f"audit_unwritten:{type(exc).__name__} batch={index} signature={result.signature}",
                file=sys.stderr,
            )
            if result.status != "confirmed":
                run.outcome = f"stopped:{result.status}"
                return _batch_code(result)
            run.outcome = "stopped:audit_unwritten_after_confirmed"
            return EX_STOPPED_AFTER_CONFIRMED
        if result.status != "confirmed":
            run.outcome = f"stopped:{result.status}"
            return _batch_code(result)
        if result.lamports_recovered < result.expected_rent - fee_allowance:
            run.outcome = "stopped:recovered_below_expected"
            print(
                f"stopped: batch {index} recovered {result.lamports_recovered} < "
                f"{result.expected_rent} - {fee_allowance}",
                file=sys.stderr,
            )
            return EX_STOPPED_AFTER_CONFIRMED
    run.outcome = "done"
    closed = sum(len(b.get("accounts", ())) for b in run.batches if b["status"] == "confirmed")
    recovered = sum(b.get("lamports_recovered", 0) for b in run.batches)
    print(
        f"done: closed={closed} lamports_recovered={recovered} signatures="
        + ",".join(str(b["signature"]) for b in run.batches if b.get("signature"))
    )
    return 0


async def apply_with(
    args: argparse.Namespace, *, session: Any, redis: Any, rpc: Any, deps: Deps
) -> int:
    run = RunLog(run_id=str(uuid7()), wallet=args.user)
    code = EX_REFUSED
    try:
        code = await _apply(args, session, redis, rpc, deps, run)
    except rules.Refused as refused:
        run.outcome = f"refused:{refused.reason}"
        print(f"refused: {refused.reason}", file=sys.stderr)
    except BaseException as exc:
        run.outcome = f"crashed:{type(exc).__name__}"
        if run.batch_in_progress is not None:  # it may have been signed and sent
            print(
                f"crashed_mid_batch batch={run.batch_in_progress} run_id={run.run_id}: look for "
                "close_atas_submitted in system_events (reason carries the run id) and check "
                "that signature on Solscan before running again",
                file=sys.stderr,
            )
        raise
    finally:
        signatures = [b["signature"] for b in run.batches if b.get("signature")]
        # a failed INSERT leaves the transaction aborted: every earlier row was
        # committed on its own, so this discards nothing (security review, 28/09)
        await rollback_quietly(session)
        try:
            await _audit(
                session,
                args,
                run,
                rules.ACTION_RUN,
                {
                    "outcome": run.outcome,
                    "kill_switch_state": run.kill_switch_state,
                    "batch_in_progress": run.batch_in_progress,
                    "signatures": signatures,
                    "batches": run.batches,
                    "lamports_recovered": sum(b.get("lamports_recovered", 0) for b in run.batches),
                },
            )
        except Exception as exc:
            print(
                f"audit_unwritten:run:{type(exc).__name__} outcome={run.outcome}", file=sys.stderr
            )
    return code


def rpc_client(args: argparse.Namespace) -> SolanaTxRpcClient:
    """Only ``--apply`` gets a client that can broadcast."""
    return (
        SolanaTxRpcClient(args.rpc, allow_send=True) if args.apply else SolanaTxRpcClient(args.rpc)
    )


async def run(args: argparse.Namespace) -> int:
    """Wiring only: the owner DSN (``DATABASE_URL_MIGRATIONS``), Redis (apply), the RPC."""
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    rpc = rpc_client(args)
    redis = create_redis(Settings()) if args.apply else None
    deps = Deps(load_signer=lambda: MemeSigner.from_environment(os.environ))
    try:
        async with AsyncSession(engine) as session:
            if args.apply:
                return await apply_with(args, session=session, redis=redis, rpc=rpc, deps=deps)
            return await dry_run_with(args, session=session, rpc=rpc, deps=deps)
    finally:
        rpc.close()
        await engine.dispose()
        if redis is not None:
            await redis.aclose()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    problem = usage_error(args)
    if problem is not None:
        print(f"usage: {problem}", file=sys.stderr)
        return EX_USAGE
    try:
        return asyncio.run(run(args))
    except rules.Refused as refused:
        print(f"refused: {refused.reason}", file=sys.stderr)
        return EX_REFUSED


if __name__ == "__main__":
    sys.exit(main())
