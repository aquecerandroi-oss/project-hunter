"""The hourly cadence around :func:`run_beta_once`, and the hand crank for it.

Two entry points, one body:

- ``beta_loop`` runs inside the scanner's TaskGroup and produces one revision per
  market per closed hour;
- ``python -m hunter_scanner_worker.beta --once`` runs exactly one pass and
  prints what it did — for the first production fill, for an operator repairing
  a missed hour after a backfill, and for the proof this task owes.

**One producer per exchange per hour, and the lock says which hour.** The key is
``beta:producer:{exchange}:{cut}``: ``SET NX`` on it decides who computes *that*
cut, and it expires on its own. A lock released at the end of the run would let
a second instance immediately redo the same hour — 200 markets of thirty-day
aggregation to write nothing — and a lock without the cut in its name would have
to be renewed by a process that is busy. Correctness never depends on it:
``uq_market_betas_revision`` makes a duplicate pass a no-op either way, so this
is a way of not wasting a database, not a way of not corrupting one. The
declared cost: a leader that dies mid-pass skips that hour, and the next hour is
computed normally by whoever takes the next key. Skipping an hour is safe by
construction — a revision is valid for one hour and admission refuses a stale
one — and it is visible as ``beta_last_run`` ageing in the heartbeat.

``--once`` deliberately takes no lock: an operator asking for a pass by hand has
already decided, and the pass is idempotent.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import TYPE_CHECKING, Any, cast

from hunter_core.domain.types import utcnow
from hunter_core.logging import configure_logging, get_logger
from hunter_core.settings import get_settings
from hunter_indicators.beta import DEFAULT_SPEC, BetaSpec, floor_bar
from hunter_scanner_worker.baseline_runner import sleep_for
from hunter_scanner_worker.beta_job import BetaHealth, BetaRun, run_beta_once
from hunter_scanner_worker.config import build_config, exchange_code

if TYPE_CHECKING:
    from datetime import datetime

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime
    from hunter_scanner_worker.scanner import Scanner

logger = get_logger(__name__)

CHECK_S = 60.0
"""How often the loop looks at the clock. ``sleep_for`` shortens it near the
turn of the hour, so a cut is picked up within seconds of closing rather than up
to a minute later."""

LOCK_TTL_S = 7_200
"""Twice the cadence: long enough that a slow pass never loses its own key, short
enough that the keys do not accumulate."""

__all__ = ["CHECK_S", "beta_loop", "main"]


def _lock_key(exchange: str, cut: datetime) -> str:
    return f"beta:producer:{exchange}:{cut.isoformat()}"


async def _claim(redis: redis_asyncio.Redis, exchange: str, cut: datetime) -> bool:
    """Whether this process is the one that computes ``cut``.

    A Redis failure answers **no**: the pass is optional (the next hour produces
    a fresh revision anyway) and two producers hammering the same window is the
    worse of the two failure modes.
    """
    try:
        return bool(await redis.set(_lock_key(exchange, cut), "1", nx=True, ex=LOCK_TTL_S))
    except Exception:
        logger.warning("scanner_beta_lock_unavailable", cut=cut.isoformat())
        return False


async def beta_loop(
    scanner: Scanner,
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
    health: BetaHealth,
    *,
    spec: BetaSpec = DEFAULT_SPEC,
) -> None:
    """One pass per closed hour, for as long as the process lives."""
    exchange = scanner.config.exchange
    computed: datetime | None = None
    while True:
        now = utcnow()
        cut = floor_bar(now, spec)
        refs = list(scanner.registry.by_symbol.values())
        if refs and (computed is None or cut > computed) and await _claim(redis, exchange, cut):
            computed = cut
            try:
                run = await run_beta_once(factory, refs, now=now, spec=spec)
                health.record(run, now=now)
                runtime.mark_success()
            except asyncio.CancelledError:
                raise
            except Exception:
                runtime.mark_error()
                logger.exception("scanner_beta_pass_failed", cut=cut.isoformat())
        await asyncio.sleep(sleep_for(now, CHECK_S))


async def _run_once(exchange: str) -> BetaRun:
    """One pass over the monitored universe, with a database of its own."""
    from hunter_core.db.session import create_engine, create_session_factory
    from hunter_core.settings import get_settings
    from hunter_scanner_worker.registry import MarketRegistry

    engine = create_engine(get_settings())
    try:
        factory = create_session_factory(engine)
        registry = MarketRegistry(exchange=exchange)
        await registry.refresh(factory, limit=build_config().max_markets)
        return await run_beta_once(
            factory, list(registry.by_symbol.values()), now=utcnow(), spec=DEFAULT_SPEC
        )
    finally:
        await engine.dispose()


def main() -> int:
    """``--once`` is required: the cadence belongs to the scanner, not to a shell.

    The output is the structured log line the pass already writes
    (``scanner_beta_pass``, with the cut, the counts per outcome and the wall
    time) plus ``scanner_beta_once`` — a worker package may not ``print``
    (ruff ``T201``), and duplicating the numbers on stdout would give an
    operator two places to read one fact.
    """
    parser = argparse.ArgumentParser(description="Produce one beta revision per monitored market.")
    parser.add_argument(
        "--once",
        action="store_true",
        required=True,
        help="run a single pass over the closed hour and exit",
    )
    parser.add_argument("--exchange", default=exchange_code(), help="exchange code to produce for")
    args = parser.parse_args()
    configure_logging(get_settings(), "scanner")
    run = asyncio.run(_run_once(cast(str, args.exchange)))
    logger.info(
        "scanner_beta_once",
        as_of=run.as_of.isoformat(),
        markets=run.markets,
        valid=run.valid_markets,
        outcomes=dict(run.outcomes),
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - the operator's entry point
    sys.exit(cast(Any, main()))
