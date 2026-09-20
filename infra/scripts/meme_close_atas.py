#!/usr/bin/env python3
"""Recover the rent of the desk wallet's EMPTY token accounts (T4.77) —
dry-run by default, ``compose.sh ops`` with ``--apply`` to run it against
the real wallet.

R64 (19/09/2026): 34 ATAs left open = 0,0514 SOL parked, because
``MEME_CLOSE_ATA_ON_FULL_SELL`` was off and no sell ever closed its ATA
(T4.46). This script lists the wallet's token accounts through
``getTokenAccountsByOwner`` (Token program **and** Token-2022), gives every
one a named verdict, and — only with ``--apply`` — closes the empty
Token-program ones in batches of at most 8 ``CloseAccount`` instructions,
built by us (no Jupiter), refund and authority both the wallet.

    # dry-run (default): the table (mint8, ata8, rent lamports, verdict) + total
    uv run python infra/scripts/meme_close_atas.py \\
        --user ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4

    # apply: one batch per run (``--max-batches``), signs with the executor's
    # own SOLANA_WALLET_SECRET_KEY (read inside the apply path only, never printed)
    bash infra/vps/compose.sh ops python infra/scripts/meme_close_atas.py --apply

    # T4.77b — Token-2022 (the 35 pump.fun ATAs, ``immutableOwner`` only):
    # opt-in, and the FIRST run is a proof run: exactly ONE Token-2022
    # account (``--limit 1 --max-batches 1`` forced, classic closes deferred
    # as ``skipped:proof_run_token_2022_only``). After it confirms on
    # mainnet, ``--i-know-2022`` unlocks the batches of 8.
    ... meme_close_atas.py --apply --token-2022
    ... meme_close_atas.py --apply --token-2022 --i-know-2022 --max-batches 5

Never closed, always listed: Token-2022 accounts without ``--token-2022``
(``skipped:token_2022``) and, with it, any Token-2022 account carrying an
extension other than ``immutableOwner`` (``skipped:token_2022_extension:<name>``)
or that is not the ATA derived with Token-2022 in the seeds (``skipped:not_ata``);
mints and multisigs (``skipped:not_token_account:<type>``); any account
with a balance (``skipped:nonzero_balance`` — dust stays), the WSOL account
when it holds lamports beyond its rent reserve (``skipped:wsol_holds_lamports``),
accounts whose owner / delegate / close authority is not the wallet
(``skipped:authority_mismatch``), frozen ones. Batches never mix programs.

``--apply`` (same discipline as ``meme_spot_swap.py``, T4.73b): the kill
switch must read exactly ``ACTIVE``; the signer is loaded after that check
and only then; every batch is verified (``meme_close_atas_verify``: only
ComputeBudget + ``CloseAccount`` to the wallet) **before** signing, simulated
with the wallet's post-state (refused unless the balance grows by
``Σ rent − fees``), signed once, audited in ``system_events`` (component
``meme_close_atas``) with the signature **before** the broadcast, sent,
confirmed for 20 × 1 s. One JSON line per batch on stdout. The priority fee
is capped at 100 000 lamports per batch. Connects with
``DATABASE_URL_MIGRATIONS`` (never the pooler) and ``REDIS_URL``; commit per
audit row.

Exit codes: 0 done (or a clean dry-run), 64 usage, 65 refused (kill switch,
user mismatch, an unparsable listing, or a batch refused by name), 66 a batch
was sent but not confirmed within the wait (reconcile by the printed
signature; the next batches did **not** run), 67 a batch failed on chain.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in ("services/meme-executor", "packages/exchange-adapters", "packages/risk-core"):
    candidate = str(REPO_ROOT / extra)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from meme_close_atas_plan import (  # noqa: E402
    BATCH_SIZE,
    Plan,
    batches,
    build_plan,
    format_table,
    list_token_accounts,
)
from meme_close_atas_send import BatchResult, result_json, run_batch  # noqa: E402
from meme_close_atas_verify import MAX_PRIORITY_FEE_LAMPORTS  # noqa: E402
from meme_ops_db import migration_url  # noqa: E402
from meme_spot_swap_kill import read_effective_kill_switch_state  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from hunter_core.domain.enums import KillSwitchState  # noqa: E402
from hunter_core.execution.meme.signer import MemeSigner  # noqa: E402
from hunter_core.redis import create_redis  # noqa: E402
from hunter_core.settings import Settings  # noqa: E402
from hunter_exchanges.pumpfun.tx_rpc import MAINNET_PUBLIC_RPC_URL, SolanaTxRpcClient  # noqa: E402

EX_USAGE = 64
EX_REFUSED = 65
EX_UNCONFIRMED = 66
EX_FAILED = 67
DEFAULT_PRIORITY_FEE_LAMPORTS = 10_000

__all__ = [
    "EX_FAILED",
    "EX_REFUSED",
    "EX_UNCONFIRMED",
    "EX_USAGE",
    "Refused",
    "apply_with",
    "main",
    "parse_args",
    "run",
]


class Refused(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--user",
        default=None,
        help="wallet public key; required for a dry-run, must match the signer on --apply",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--max-batches", type=int, default=1, help="batches of <= 8 closes")
    parser.add_argument("--limit", type=int, default=None, help="at most this many accounts")
    parser.add_argument(
        "--priority-fee-lamports",
        type=int,
        default=DEFAULT_PRIORITY_FEE_LAMPORTS,
        help=f"per batch, capped at {MAX_PRIORITY_FEE_LAMPORTS}",
    )
    parser.add_argument(
        "--token-2022",
        action="store_true",
        help="also close EMPTY Token-2022 accounts (immutableOwner only); first run = 1 account",
    )
    parser.add_argument(
        "--i-know-2022",
        action="store_true",
        help="after one Token-2022 close confirmed on mainnet: lift the 1-account proof run",
    )
    parser.add_argument("--reason", default="T4.77 recover empty ATA rent")
    parser.add_argument("--actor", default="everton", help="who is running it (audit row)")
    parser.add_argument("--rpc", default=MAINNET_PUBLIC_RPC_URL)
    return parser.parse_args(argv)


def usage_error(args: argparse.Namespace) -> str | None:
    if not args.apply and not args.user:
        return "--user <wallet pubkey> is required for a dry-run"
    if args.max_batches < 1:
        return "--max-batches must be >= 1"
    if args.limit is not None and args.limit < 1:
        return "--limit must be >= 1"
    if not 0 <= args.priority_fee_lamports <= MAX_PRIORITY_FEE_LAMPORTS:
        return f"--priority-fee-lamports must be in 0..{MAX_PRIORITY_FEE_LAMPORTS}"
    if args.i_know_2022 and not args.token_2022:
        return "--i-know-2022 only makes sense with --token-2022"
    if _proof_run(args) and (args.limit not in (None, 1) or args.max_batches != 1):
        return (
            "the first --token-2022 run closes exactly 1 account (--limit 1 --max-batches 1); "
            "drop those flags, or add --i-know-2022 after one Token-2022 close confirmed"
        )
    return None


def _proof_run(args: argparse.Namespace) -> bool:
    return bool(args.token_2022 and not args.i_know_2022)


def _plan(rpc: Any, wallet: str, args: argparse.Namespace) -> Plan:
    try:
        rows = list_token_accounts(rpc, wallet)
    except ValueError as exc:
        raise Refused(f"listing_unparsable:{exc}") from exc
    proof = _proof_run(args)
    return build_plan(
        rows,
        wallet=wallet,
        limit=1 if proof else args.limit,
        token_2022=bool(args.token_2022),
        proof_run=proof,
    )


def _print_plan(plan: Plan, *, args: argparse.Namespace) -> tuple[tuple[Any, ...], ...]:
    print(format_table(plan))
    parts = batches(plan)
    max_batches = 1 if _proof_run(args) else args.max_batches
    print(
        f"batches={len(parts)} batch_size={BATCH_SIZE} this_run_max_batches={max_batches} "
        f"accounts_this_run={sum(len(p) for p in parts[:max_batches])}"
    )
    if _proof_run(args):
        print(
            "proof_run=token_2022: this run closes at most 1 Token-2022 account; once it is "
            "confirmed on mainnet, re-run with --i-know-2022 for the batches of 8"
        )
    return parts[:max_batches]


def _dry_run(args: argparse.Namespace) -> int:
    rpc = SolanaTxRpcClient(args.rpc)  # no allow_send: this client cannot broadcast
    try:
        plan = _plan(rpc, args.user, args)
        _print_plan(plan, args=args)
    finally:
        rpc.close()
    print("dry-run: nothing written (add --apply)")
    return 0


async def apply_with(
    args: argparse.Namespace,
    *,
    conn: Any,
    redis: Any,
    rpc: Any,
    load_signer: Callable[[], MemeSigner],
) -> int:
    """The ``--apply`` logic with every side effect injected: the kill
    switch is read before the signer is loaded **and again before every
    batch** (Astra, T4.77 review: an EMERGENCY thrown while batch 0 confirms
    must stop batch 1 before it is signed); the listing is taken for the
    signer's own public key; batches run in order and stop at the first one
    that is not ``confirmed``."""

    async def require_active() -> None:
        state = await read_effective_kill_switch_state(conn, redis)
        if state != KillSwitchState.ACTIVE:
            raise Refused(f"kill_switch_not_active:{state.value}")

    await require_active()
    signer = load_signer()
    wallet = signer.pubkey
    if args.user and args.user != wallet:
        raise Refused(f"user_mismatch:{args.user[:8]}!={wallet[:8]}")
    plan = _plan(rpc, wallet, args)
    parts = _print_plan(plan, args=args)
    if not parts:
        print("nothing to close")
        return 0
    closed = 0
    recovered = 0
    for index, batch in enumerate(parts):
        if index:
            await require_active()
        result = await run_batch(
            conn,
            rpc,
            signer,
            batch=batch,
            reason=args.reason,
            actor=args.actor,
            priority_fee_lamports=args.priority_fee_lamports,
        )
        print(result_json(result, batch_index=index), flush=True)
        if result.status != "confirmed":
            return _exit_code(result)
        closed += result.n_closed
        recovered += result.lamports_recovered
    print(f"done: closed={closed} lamports_recovered={recovered}")
    return 0


def _exit_code(result: BatchResult) -> int:
    return {"submitted": EX_UNCONFIRMED, "failed": EX_FAILED}.get(result.status, EX_REFUSED)


async def _apply(args: argparse.Namespace) -> int:
    """Wiring only: owner connection (commit-as-you-go, never an enclosing
    transaction), Redis, the send-enabled RPC, the signer factory."""
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    redis = create_redis(Settings())
    rpc = SolanaTxRpcClient(args.rpc, allow_send=True)
    try:
        async with engine.connect() as conn:
            return await apply_with(
                args,
                conn=conn,
                redis=redis,
                rpc=rpc,
                load_signer=lambda: MemeSigner.from_environment(os.environ),
            )
    finally:
        rpc.close()
        await engine.dispose()
        await redis.aclose()


async def run(args: argparse.Namespace) -> int:
    return await _apply(args) if args.apply else _dry_run(args)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    problem = usage_error(args)
    if problem is not None:
        print(f"usage: {problem}", file=sys.stderr)
        return EX_USAGE
    try:
        return asyncio.run(run(args))
    except Refused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return EX_REFUSED


if __name__ == "__main__":
    sys.exit(main())
