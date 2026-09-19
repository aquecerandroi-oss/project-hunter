#!/usr/bin/env python3
"""Audited spot swap through Jupiter, any mint pair (T4.73) — dry-run by
default, ``compose.sh ops`` to run it against a real wallet.

Everton, 19/09/2026 10:2x BRT: use Binance as the signal source and buy on
Solana through the wallet via Jupiter — "faca um teste". Generalizes T4.54's
USDC->SOL treasury top-up (``hunter_meme_executor.treasury*``, kept
untouched) into a manual, one-shot tool for *any* pair, reusing the same
table (``meme_treasury_swaps``, ``0056``'s ``input_mint``/``output_mint``),
the same verify-before-sign discipline (``hunter_meme_executor.spot_verify``,
``meme_spot_swap_plan.py``/``meme_spot_swap_send.py``) and the same
simulate-with-accounts balance invariant (``meme_spot_swap_rules.py``).

    # dry-run (default): quote, route, impact, expected out, verifier verdict
    uv run python infra/scripts/meme_spot_swap.py --from SOL --to \\
        EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm --amount 0.02 \\
        --reason "T4.73 teste" --user ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4

    # the same, round trip (buy then a fresh quote to sell straight back)
    uv run python infra/scripts/meme_spot_swap.py --from SOL --to <mint> \\
        --amount 0.02 --round-trip --reason "..." --user <pubkey>

    # apply -- signs with the executor's own SOLANA_WALLET_SECRET_KEY, never printed
    bash infra/vps/compose.sh ops python infra/scripts/meme_spot_swap.py \\
        --from SOL --to <mint> --amount 0.02 --apply --reason "..."

Caps (fail closed, refused by name before anything is built): ``--amount`` is
capped at 0,05 SOL-equivalent unless ``--i-know``, and at 0,10 SOL-equivalent
**no matter what** (T4.73b: ``--i-know`` lifts the soft cap only); a pair
with no SOL leg has no computable SOL-equivalent and is refused the same way;
price impact above ``--max-impact-pct`` (default 1%) on **every** leg, the
sell-back included; a SOL buy leg must leave ``wallet - amount - 0,01 >=
MEME_WALLET_MIN_SOL_AFTER_SWAP`` (default 0,30 SOL); ``--apply`` refuses
unless the kill switch reads exactly ``ACTIVE`` (stricter than the executor's
own gate, which still trades under ``WARNING``) and refuses on the verifier's
verdict of the plan before a second ``POST /swap``. ``--apply`` only ever
supports a leg that is native SOL (buy with SOL, or sell for SOL) -- a
token->token ``--apply`` is refused (``apply_requires_a_sol_leg``); the
dry-run quote/verify path has no such limit. Connects with
``DATABASE_URL_MIGRATIONS`` (never the pooler) and ``REDIS_URL``, like every
other ops script; the signer is read exactly once, after the kill switch, the
same way ``treasury_send`` does, and is never rendered. Every row write is
committed on its own (T4.73b): a leg whose confirmation is still pending
after 20 s stays ``submitted`` with its signature printed, exits 66 and never
fires the sell-back -- reconcile by signature. The sell-back re-reads the kill
switch after ``--hold-s``; it is an exit, so it proceeds under any state and
the state is printed.

Exit codes: 0 done (or a clean dry-run), 64 usage, 65 refused (before or
inside a leg), 66 a leg was sent but not confirmed within the wait (row
``submitted`` — reconcile by signature), 67 a leg failed on chain.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Callable, Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in ("services/meme-executor", "packages/exchange-adapters", "packages/risk-core"):
    candidate = str(REPO_ROOT / extra)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from meme_ops_db import migration_url  # noqa: E402
from meme_spot_swap_kill import read_effective_kill_switch_state  # noqa: E402
from meme_spot_swap_plan import Refused, build_plan, format_plan, read_mint_decimals  # noqa: E402
from meme_spot_swap_rules import (  # noqa: E402
    DEFAULT_MAX_IMPACT_PCT,
    ENV_WALLET_MIN_SOL_AFTER_SWAP,
    classify_wallet_floor,
    parse_wallet_floor,
    to_atoms,
)
from meme_spot_swap_send import LegResult, run_apply_leg  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from hunter_core.domain.enums import KillSwitchState  # noqa: E402
from hunter_core.execution.meme.signer import MemeSigner  # noqa: E402
from hunter_core.logging import get_logger  # noqa: E402
from hunter_core.redis import create_redis  # noqa: E402
from hunter_core.settings import Settings  # noqa: E402
from hunter_exchanges.jupiter import JupiterClient  # noqa: E402
from hunter_exchanges.jupiter.models import WRAPPED_SOL_MINT  # noqa: E402
from hunter_exchanges.jupiter.spot import resolve_mint  # noqa: E402
from hunter_exchanges.pumpfun.tx_rpc import MAINNET_PUBLIC_RPC_URL, SolanaTxRpcClient  # noqa: E402
from hunter_meme_executor.chain import ChainReader  # noqa: E402

EX_REFUSED = 65
EX_UNCONFIRMED = 66
EX_FAILED = 67
LAMPORTS = Decimal(1_000_000_000)

__all__ = [
    "EX_FAILED",
    "EX_REFUSED",
    "EX_UNCONFIRMED",
    "Refused",
    "apply_with",
    "main",
    "parse_args",
    "run",
]

logger = get_logger("meme_spot_swap")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--from", dest="from_", required=True, help='"SOL" or a mint address')
    parser.add_argument("--to", required=True, help='"SOL" or a mint address')
    parser.add_argument("--amount", required=True, help="decimal, human units of --from")
    parser.add_argument("--slippage-bps", type=int, default=50)
    parser.add_argument("--max-impact-pct", default=str(DEFAULT_MAX_IMPACT_PCT))
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--i-know", action="store_true")
    parser.add_argument("--round-trip", action="store_true")
    parser.add_argument("--hold-s", type=float, default=0.0)
    parser.add_argument("--user", default=None, help="public key only, for a dry-run's verify step")
    parser.add_argument("--rpc", default=MAINNET_PUBLIC_RPC_URL)
    return parser.parse_args(argv)


async def _dry_run(args: argparse.Namespace) -> int:
    input_mint, output_mint = resolve_mint(args.from_), resolve_mint(args.to)
    rpc = SolanaTxRpcClient(args.rpc)
    in_decimals = read_mint_decimals(rpc, input_mint)
    out_decimals = read_mint_decimals(rpc, output_mint)
    amount_atoms = to_atoms(Decimal(args.amount), in_decimals)
    with JupiterClient() as client:
        plan = build_plan(
            client,
            input_mint=input_mint,
            output_mint=output_mint,
            amount_atoms=amount_atoms,
            slippage_bps=args.slippage_bps,
            max_impact_pct=Decimal(args.max_impact_pct),
            i_know=args.i_know,
            wallet_pubkey=args.user,
        )
        print(format_plan(plan, in_decimals=in_decimals, out_decimals=out_decimals))
        if args.round_trip:
            back_amount = int(plan.quote.other_amount_threshold)
            back = build_plan(
                client,
                input_mint=output_mint,
                output_mint=input_mint,
                amount_atoms=back_amount,
                slippage_bps=args.slippage_bps,
                max_impact_pct=Decimal(args.max_impact_pct),
                i_know=True,
                wallet_pubkey=args.user,
            )
            print("round-trip sell-back:")
            print(format_plan(back, in_decimals=out_decimals, out_decimals=in_decimals))
            cost = Decimal(amount_atoms - int(back.quote.out_amount)) / Decimal(amount_atoms)
            print(f"round_trip_cost_fraction={cost}")
    refusals = [r for r in (plan.amount_cap_refusal, plan.impact_refusal) if r]
    if refusals:
        print(f"dry-run: would refuse: {', '.join(refusals)}")
    else:
        print("dry-run: nothing written (add --apply)")
    return 0


async def apply_with(
    args: argparse.Namespace,
    *,
    conn: Any,
    redis: Any,
    chain: ChainReader,
    client: Any,
    load_signer: Callable[[], MemeSigner],
    env: Mapping[str, str],
) -> int:
    """The ``--apply`` logic with every side effect injected (T4.73b): the
    kill switch is read before the signer is loaded; the wallet floor, the
    caps and the plan's verifier verdict all refuse before the first leg."""
    input_mint, output_mint = _apply_pair(args)
    state = await read_effective_kill_switch_state(conn, redis)
    if state != KillSwitchState.ACTIVE:
        raise Refused(f"kill_switch_not_active:{state.value}")
    signer = load_signer()
    in_decimals = read_mint_decimals(chain.rpc, input_mint)
    amount_atoms = to_atoms(Decimal(args.amount), in_decimals)
    max_impact_pct = Decimal(args.max_impact_pct)
    if input_mint == WRAPPED_SOL_MINT:
        try:
            floor = parse_wallet_floor(env.get(ENV_WALLET_MIN_SOL_AFTER_SWAP))
        except ValueError as exc:
            raise Refused(f"wallet_floor_invalid:{exc}") from exc
        wallet_sol = Decimal(chain.wallet(signer.pubkey).lamports) / LAMPORTS
        floor_refusal = classify_wallet_floor(
            wallet_sol=wallet_sol, amount_sol=Decimal(args.amount), floor=floor
        )
        if floor_refusal is not None:
            raise Refused(floor_refusal)
    plan = build_plan(
        client,
        input_mint=input_mint,
        output_mint=output_mint,
        amount_atoms=amount_atoms,
        slippage_bps=args.slippage_bps,
        max_impact_pct=max_impact_pct,
        i_know=args.i_know,
        wallet_pubkey=signer.pubkey,
    )
    for refusal in (plan.amount_cap_refusal, plan.impact_refusal, plan.verify_reason):
        if refusal:
            raise Refused(refusal)
    leg = await run_apply_leg(
        conn,
        chain,
        client,
        signer,
        reason=args.reason,
        input_mint=input_mint,
        output_mint=output_mint,
        amount_atoms=amount_atoms,
        slippage_bps=args.slippage_bps,
        max_impact_pct=max_impact_pct,
    )
    _print_leg("buy leg", leg)
    if leg.status != "confirmed" or not args.round_trip:
        return _exit_code(leg)
    if leg.filled <= 0:
        print("sell-back skipped: nothing filled on the buy leg")
        return 0
    if args.hold_s > 0:
        await asyncio.sleep(args.hold_s)
    state = await read_effective_kill_switch_state(conn, redis)
    if state != KillSwitchState.ACTIVE:
        # An exit is never blocked by an entry lock (docs/RISK_ENGINE_MEME.md §7):
        # the sell-back proceeds; the state is on record.
        logger.warning("meme_spot_swap_kill_switch_changed_during_hold", state=state.value)
        print(f"kill switch now {state.value}: sell-back proceeds (exit)")
    back = await run_apply_leg(
        conn,
        chain,
        client,
        signer,
        reason=args.reason,
        input_mint=output_mint,
        output_mint=input_mint,
        amount_atoms=leg.filled,
        slippage_bps=args.slippage_bps,
        max_impact_pct=max_impact_pct,
    )
    _print_leg("sell-back leg", back)
    return _exit_code(back)


def _print_leg(label: str, leg: LegResult) -> None:
    print(f"{label}: {leg.status} filled={leg.filled} signature={leg.signature}")


def _exit_code(leg: LegResult) -> int:
    return {"confirmed": 0, "submitted": EX_UNCONFIRMED, "failed": EX_FAILED}.get(
        leg.status, EX_REFUSED
    )


def _apply_pair(args: argparse.Namespace) -> tuple[str, str]:
    input_mint, output_mint = resolve_mint(args.from_), resolve_mint(args.to)
    if WRAPPED_SOL_MINT not in (input_mint, output_mint):
        raise Refused("apply_requires_a_sol_leg")
    return input_mint, output_mint


async def _apply(args: argparse.Namespace) -> int:
    """Wiring only: owner connection (commit-as-you-go, never an enclosing
    transaction -- T4.73b), Redis, the send-enabled RPC, the Jupiter client."""
    _apply_pair(args)  # refused before any engine, Redis or RPC exists
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    redis = create_redis(Settings())
    try:
        async with engine.connect() as conn:
            rpc = SolanaTxRpcClient(args.rpc, allow_send=True)
            with JupiterClient() as client:
                return await apply_with(
                    args,
                    conn=conn,
                    redis=redis,
                    chain=ChainReader(rpc),
                    client=client,
                    load_signer=lambda: MemeSigner.from_environment(os.environ),
                    env=os.environ,
                )
    finally:
        await engine.dispose()
        await redis.aclose()


async def run(args: argparse.Namespace) -> int:
    return await (_apply(args) if args.apply else _dry_run(args))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return asyncio.run(run(args))
    except Refused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return EX_REFUSED


if __name__ == "__main__":
    sys.exit(main())
