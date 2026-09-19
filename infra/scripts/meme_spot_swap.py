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
capped at 0,05 SOL-equivalent unless ``--i-know``; a pair with no SOL leg has
no computable SOL-equivalent and is refused the same way; price impact above
``--max-impact-pct`` (default 1%); ``--apply`` refuses unless the kill switch
reads exactly ``ACTIVE`` (stricter than the executor's own gate, which still
trades under ``WARNING``). ``--apply`` only ever supports a leg that is native
SOL (buy with SOL, or sell for SOL) -- a token->token ``--apply`` is refused
(``apply_requires_a_sol_leg``); the dry-run quote/verify path has no such
limit. Connects with ``DATABASE_URL_MIGRATIONS`` (never the pooler) and
``REDIS_URL``, like every other ops script; the signer is read exactly once,
the same way ``treasury_send`` does, and is never rendered.

Exit codes: 0 done (or a clean dry-run), 64 usage, 65 refused.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in ("services/meme-executor", "packages/exchange-adapters", "packages/risk-core"):
    candidate = str(REPO_ROOT / extra)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from meme_ops_db import migration_url  # noqa: E402
from meme_spot_swap_kill import read_effective_kill_switch_state  # noqa: E402
from meme_spot_swap_plan import Refused, build_plan, format_plan, read_mint_decimals  # noqa: E402
from meme_spot_swap_rules import DEFAULT_MAX_IMPACT_PCT, to_atoms  # noqa: E402
from meme_spot_swap_send import run_apply_leg  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from hunter_core.domain.enums import KillSwitchState  # noqa: E402
from hunter_core.execution.meme.signer import MemeSigner  # noqa: E402
from hunter_core.redis import create_redis  # noqa: E402
from hunter_core.settings import Settings  # noqa: E402
from hunter_exchanges.jupiter import JupiterClient  # noqa: E402
from hunter_exchanges.jupiter.models import WRAPPED_SOL_MINT  # noqa: E402
from hunter_exchanges.jupiter.spot import resolve_mint  # noqa: E402
from hunter_exchanges.pumpfun.tx_rpc import MAINNET_PUBLIC_RPC_URL, SolanaTxRpcClient  # noqa: E402
from hunter_meme_executor.chain import ChainReader  # noqa: E402

EX_REFUSED = 65

__all__ = ["Refused", "main", "parse_args", "run"]


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


async def _apply(args: argparse.Namespace) -> int:
    input_mint, output_mint = resolve_mint(args.from_), resolve_mint(args.to)
    if WRAPPED_SOL_MINT not in (input_mint, output_mint):
        raise Refused("apply_requires_a_sol_leg")
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    redis = create_redis(Settings())
    try:
        async with engine.connect() as conn, conn.begin():
            state = await read_effective_kill_switch_state(conn, redis)
            if state != KillSwitchState.ACTIVE:
                raise Refused(f"kill_switch_not_active:{state.value}")
            signer = MemeSigner.from_environment(os.environ)
            rpc = SolanaTxRpcClient(args.rpc, allow_send=True)
            chain = ChainReader(rpc)
            in_decimals = read_mint_decimals(rpc, input_mint)
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
                    wallet_pubkey=signer.pubkey,
                )
                if plan.amount_cap_refusal or plan.impact_refusal:
                    raise Refused(plan.amount_cap_refusal or plan.impact_refusal or "refused")
                status, filled = await run_apply_leg(
                    conn,
                    chain,
                    client,
                    signer,
                    reason=args.reason,
                    input_mint=input_mint,
                    output_mint=output_mint,
                    amount_atoms=amount_atoms,
                    slippage_bps=args.slippage_bps,
                )
                print(f"buy leg: {status} filled={filled}")
                if status == "confirmed" and args.round_trip:
                    if args.hold_s > 0:
                        await asyncio.sleep(args.hold_s)
                    status2, filled2 = await run_apply_leg(
                        conn,
                        chain,
                        client,
                        signer,
                        reason=args.reason,
                        input_mint=output_mint,
                        output_mint=input_mint,
                        amount_atoms=filled,
                        slippage_bps=args.slippage_bps,
                    )
                    print(f"sell-back leg: {status2} filled={filled2}")
        return 0
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
