"""``python -m hunter_strategy_worker.replay.run`` — the replay job.

    uv run python -m hunter_strategy_worker.replay.run \
        --version <strategy_version_id | key:version> \
        --from 2026-08-08 --to 2026-09-08 \
        --markets all | BTCUSDT,ETHUSDT \
        [--cohort replay:<uuid>] [--workers N] [--ledger path.jsonl] \
        [--explain-ledger explain.jsonl] [--dry-run]

    uv run python -m hunter_strategy_worker.replay.run --drain-queue [--max-runs 1]

    uv run python -m hunter_strategy_worker.replay.run --stress replay:<uuid> \
        [--as-of ISO] [--ledger stress.jsonl]

``--stress`` não replaya nada: ele **reprecifica** a coorte que um replay já
deixou gravada, sob custo dobrado, stop e alvo escalados, entrada atrasada,
cada mercado de fora e cada metade da janela (T3.36,
:mod:`hunter_strategy_worker.replay.stress`). A sessão é ``READ ONLY``; a
bandeira está aqui porque a passada de estresse é o passo seguinte do mesmo
funil, e quem acabou de rodar um replay não deveria precisar procurar outro
comando.

Nothing here activates, promotes or sizes anything, and no row it writes can
reach a wallet: every decision carries ``replay:<run_id>``, the execution bridge
refuses that cohort by name (``cohort_not_live``) and, since T3.19b, a replay
decision does not even get an outbox row to be refused.

**Parallel by market, in processes and not threads.** One replayed bar spends
its time in ``Decimal`` arithmetic inside ``Strategy.explain`` — CPU under the
GIL — so threads would serialise exactly the part that costs. Markets are the
natural axis because the state a replay mutates is keyed by
``(version, market, cohort)``: two processes on two markets never touch the same
episode slot, the same signal identity or the same tracking. Two processes on
the *same* market would, and the pool never does that.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from hunter_core.db.session import create_engine, create_session_factory, role_session
from hunter_core.domain.enums import ShadowCohort
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_core.settings import Settings
from hunter_strategy_worker.replay.budget import (
    ReplayBudget,
    ReplayRequest,
    live_lane_degraded,
    load_budget,
    refuse_direct_run,
    take_next,
    workers_for,
)
from hunter_strategy_worker.replay.environment import REPLAY_DECISION_LAG_S
from hunter_strategy_worker.replay.explain import ledger_for, merge_markets
from hunter_strategy_worker.replay.ledger import ReplayRun, append_jsonl, record_run
from hunter_strategy_worker.replay.plan import (
    RunPlan,
    config_for,
    day,
    resolve_markets,
    resolve_version,
)
from hunter_strategy_worker.replay.simulate import (
    MarketReplay,
    ReplayWindow,
    count_population,
    drain_cohort,
    replay_market,
)
from hunter_strategy_worker.replay.stress import run_cli as stress_cli

logger = get_logger(__name__)

__all__ = ["main", "replay_run"]


async def _one_market(payload: dict[str, Any]) -> dict[str, Any]:
    """Replay one market in this process; the unit the pool hands out."""
    settings = Settings()
    engine = create_engine(settings)
    try:
        factory = create_session_factory(engine)
        version = await resolve_version(factory, payload["version"])
        markets = await resolve_markets(
            factory, exchange=payload["exchange"], symbols=payload["symbol"]
        )
        window = ReplayWindow(
            datetime.fromisoformat(payload["start"]), datetime.fromisoformat(payload["end"])
        )
        market = markets[0]
        with ledger_for(
            payload.get("explain"), exchange=market.exchange, symbol=market.symbol
        ) as ledger:
            result = await replay_market(
                factory,
                version=version,
                market=market,
                window=window,
                config=config_for(payload["cohort"]),
                lag_s=int(payload["lag_s"]),
                explain=ledger,
            )
        return {"bars": result.bars, "states": result.states, "errors": result.errors}
    finally:
        await engine.dispose()


def _worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Process-pool entry point: one event loop per market, then teardown."""
    return asyncio.run(_one_market(payload))


async def replay_run(
    plan: RunPlan,
    *,
    workers: int,
    ledger_path: Path | None,
    explain_path: Path | None = None,
) -> ReplayRun:
    """Run the whole plan and write its ledger row. Returns the row.

    ``explain_path`` turns on the explain ledger (T3.33f): one JSONL line per
    evaluated bar with the strategy's own state, reason and detail. Each market
    process writes its own shard and the parent concatenates them here, in the
    order the markets were dispatched, appending to the file — a run sliced in
    two writes one ledger.
    """
    started = utcnow()
    clock = time.perf_counter()
    payloads = [
        {
            "version": str(plan.version.id),
            "exchange": market.exchange,
            "symbol": market.symbol,
            "start": plan.window.start.isoformat(),
            "end": plan.window.end.isoformat(),
            "cohort": plan.cohort,
            "lag_s": plan.lag_s,
            "explain": str(explain_path) if explain_path is not None else None,
        }
        for market in plan.markets
    ]
    totals = MarketReplay()
    pool_size = max(1, min(workers, len(payloads)))
    if pool_size == 1:
        for payload in payloads:
            totals.merge(_as_result(await _one_market(payload)))
    else:
        loop = asyncio.get_running_loop()
        with ProcessPoolExecutor(max_workers=pool_size) as pool:
            for outcome in await asyncio.gather(
                *(loop.run_in_executor(pool, _worker, payload) for payload in payloads)
            ):
                totals.merge(_as_result(outcome))

    settings = Settings()
    engine = create_engine(settings)
    try:
        factory = create_session_factory(engine)
        config = config_for(plan.cohort)
        still_open = await drain_cohort(factory, cohort=plan.cohort, config=config)
        async with role_session(factory, db_role="hunter_worker") as session:
            population = await count_population(
                session, cohort=plan.cohort, strategy_version_id=plan.version.id
            )
        run = ReplayRun(
            run_id=uuid.UUID(plan.cohort.removeprefix(ShadowCohort.REPLAY_PREFIX)),
            cohort=plan.cohort,
            strategy_version_id=plan.version.id,
            version_label=f"{plan.version.strategy_key} {plan.version.version}",
            window_from=plan.window.start,
            window_to=plan.window.end,
            markets=tuple(f"{m.exchange}:{m.symbol}" for m in plan.markets),
            started_at=started,
            finished_at=utcnow(),
            bars_evaluated=totals.bars,
            signals=population.signals,
            outcomes_resolved=population.outcomes,
            outcomes_open=max(population.open, still_open),
            seconds=time.perf_counter() - clock,
            decision_lag_s=plan.lag_s,
            workers=pool_size,
            evaluations_by_state=dict(totals.states),
            errors=totals.errors,
            context_minutes=plan.context_minutes,
        )
        async with role_session(factory, db_role="hunter_worker") as session:
            await record_run(session, run)
    finally:
        await engine.dispose()
    if ledger_path is not None:
        append_jsonl(ledger_path, run)
    if explain_path is not None:
        merge_markets(
            explain_path,
            [(market.exchange, market.symbol) for market in plan.markets],
            bars=run.bars_evaluated,
        )
    return run


def _as_result(payload: dict[str, Any]) -> MarketReplay:
    result = MarketReplay(bars=int(payload["bars"]), errors=int(payload["errors"]))
    result.states = {str(k): int(v) for k, v in dict(payload["states"]).items()}
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hunter_strategy_worker.replay.run", description=__doc__)
    parser.add_argument("--version", help="strategy_version_id or <key>:<version>")
    parser.add_argument("--from", dest="start", help="window start (UTC, inclusive)")
    parser.add_argument("--to", dest="end", help="window end (UTC, exclusive)")
    parser.add_argument("--markets", default="all", help="'all' or SYMBOL,SYMBOL")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--cohort", default=None, help="replay:<uuid>; minted when omitted")
    parser.add_argument("--workers", type=int, default=None, help="override the budget's pool")
    parser.add_argument("--lag-s", type=int, default=REPLAY_DECISION_LAG_S)
    parser.add_argument("--ledger", default=None, help="JSONL ledger to append the run to")
    parser.add_argument(
        "--explain-ledger",
        default=None,
        help="JSONL file to append one line per evaluated bar (state, reason, detail)",
    )
    parser.add_argument("--dry-run", action="store_true", help="resolve and count, write nothing")
    parser.add_argument("--drain-queue", action="store_true", help="run what the queue holds")
    parser.add_argument("--max-runs", type=int, default=1)
    parser.add_argument("--stress", default=None, help="reprice an existing replay:<uuid> (T3.36)")
    parser.add_argument("--as-of", default=None, help="data cut of --stress (UTC); default: now")
    return parser


async def _plan_from(args: argparse.Namespace, cohort: str, factory: Any) -> RunPlan:
    version = await resolve_version(factory, str(args.version))
    markets = await resolve_markets(factory, exchange=str(args.exchange), symbols=str(args.markets))
    if not markets:
        raise SystemExit("no market matched the selection")
    return RunPlan(
        version=version,
        markets=markets,
        window=ReplayWindow(day(str(args.start)), day(str(args.end))),
        cohort=cohort,
        lag_s=int(args.lag_s),
    )


async def _drain(args: argparse.Namespace, budget: ReplayBudget) -> list[ReplayRun]:
    """Take up to ``--max-runs`` requests off the queue and run them.

    Checked **before** ``take_next``, not after (T3.74): the readiness gate
    existed and was tested but nothing here ever called it, so a drain kept
    slicing at full budget while live decision lag passed two minutes on
    09-10/09; checking after would pop a request and then lose it.
    """
    from hunter_core.redis import create_redis

    settings = Settings()
    redis = create_redis(settings)
    engine = create_engine(settings)
    runs: list[ReplayRun] = []
    try:
        factory = create_session_factory(engine)
        limit = min(int(args.max_runs), budget.max_concurrent_runs)
        for _ in range(max(1, limit)):
            reason = await live_lane_degraded(redis, budget)
            if reason is not None:
                logger.warning("replay_drain_paused_live_lane_degraded", reason=reason)
                break
            request: ReplayRequest | None = await take_next(redis, key=budget.queue_key)
            if request is None:
                break
            args.version = str(request.strategy_version_id)
            args.markets = ",".join(request.markets) if request.markets else "all"
            args.start = request.window_from.isoformat()
            args.end = request.window_to.isoformat()
            plan = await _plan_from(args, request.cohort, factory)
            runs.append(await _run(args, plan, budget))
    finally:
        await engine.dispose()
        await redis.aclose()
    return runs


async def _run(args: argparse.Namespace, plan: RunPlan, budget: ReplayBudget) -> ReplayRun:
    workers = int(args.workers) if args.workers else workers_for(budget, os.cpu_count() or 1)
    ledger = Path(str(args.ledger)) if args.ledger else None
    explain = Path(str(args.explain_ledger)) if args.explain_ledger else None
    run = await replay_run(plan, workers=workers, ledger_path=ledger, explain_path=explain)
    sys.stdout.write(f"{run.to_jsonable()}\n")
    return run


async def _main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    budget = load_budget()
    if args.stress:
        forwarded = ["--cohort", str(args.stress)]
        if args.as_of:
            forwarded += ["--as-of", str(args.as_of)]
        if args.ledger:
            forwarded += ["--ledger", str(args.ledger)]
        return await stress_cli(forwarded)
    if args.drain_queue:
        return 0 if await _drain(args, budget) else 1
    if not (args.version and args.start and args.end):
        raise SystemExit("--version, --from and --to are required without --drain-queue")
    cohort = str(args.cohort) if args.cohort else ShadowCohort.replay(uuid.uuid4())
    settings = Settings()
    if not args.dry_run and (reason := await refuse_direct_run(settings, budget)) is not None:
        sys.stdout.write(f"refused: live lane degraded ({reason})\n")
        return 1
    engine = create_engine(settings)
    try:
        plan = await _plan_from(args, cohort, create_session_factory(engine))
    finally:
        await engine.dispose()
    if args.dry_run:
        sys.stdout.write(
            f"{{'cohort': '{plan.cohort}', 'version': '{plan.version.strategy_key} "
            f"{plan.version.version}', 'markets': {len(plan.markets)}, "
            f"'bars_planned': {plan.bars_planned}, "
            f"'context_minutes': {plan.context_minutes}, "
            f"'workers': {int(args.workers) if args.workers else workers_for(budget, os.cpu_count() or 1)}}}\n"
        )
        return 0
    await _run(args, plan, budget)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Console entry point."""
    return asyncio.run(_main(argv))


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
