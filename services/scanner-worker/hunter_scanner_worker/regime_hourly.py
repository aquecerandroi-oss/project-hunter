"""The hourly cadence around :func:`run_regime_once`, and the hand crank for it.

Two entry points, one body — the shape ``beta.py`` already uses, for the same
reasons:

- ``regime_hourly_loop`` runs inside the scanner's TaskGroup and produces the
  hour that just closed (and, on the first pass of a fresh database, the
  thirty-one days behind it);
- ``python -m hunter_scanner_worker.regime_hourly --once`` runs exactly one pass
  and exits — for the first production fill, for an operator repairing hours
  after a candle backfill, and for the proof this task owes.

**One producer per exchange per hour, and the lock names the hour.** The key is
``regime:producer:{exchange}:{cut}``: ``SET NX`` decides who computes *that* cut
and it expires on its own. Correctness does not depend on it — the digest makes a
duplicate pass an ``unchanged`` — but ``market_regimes`` has no unique index on
``(scope, start_time)`` yet, so two producers starting the same second could each
insert the same hour. Until the index exists (brief filed), this lock is the only
thing standing between that race and a duplicated hour, and that is written down
rather than assumed. The declared cost is the same as beta's: a leader that dies
mid-pass skips the hour, and the next pass produces it as a *missing* hour, which
is exactly what the backfill rule already does.

``--once`` deliberately takes no lock: an operator asking for a pass by hand has
already decided, and the pass is idempotent by digest.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import TYPE_CHECKING, Any, cast

from hunter_core.domain.types import utcnow
from hunter_core.logging import configure_logging, get_logger
from hunter_core.settings import get_settings
from hunter_indicators.regime import DEFAULT_HOURLY_THRESHOLDS
from hunter_scanner_worker.baseline_runner import sleep_for
from hunter_scanner_worker.config import build_config, exchange_code
from hunter_scanner_worker.regime_job import (
    BACKFILL_DAYS,
    RegimeHealth,
    RegimeRun,
    floor_hour,
    run_regime_once,
)

if TYPE_CHECKING:
    from datetime import datetime

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime
    from hunter_indicators.regime import HourlyThresholds
    from hunter_scanner_worker.scanner import Scanner

logger = get_logger(__name__)

CHECK_S = 60.0
"""How often the loop looks at the clock. ``sleep_for`` shortens it near the turn
of the hour, so a cut is picked up within seconds of closing."""

LOCK_TTL_S = 7_200
"""Twice the cadence: long enough that a slow first pass (thirty-one days) never
loses its own key, short enough that the keys do not accumulate."""

__all__ = ["CHECK_S", "main", "regime_hourly_loop"]


def _lock_key(exchange: str, cut: datetime) -> str:
    return f"regime:producer:{exchange}:{cut.isoformat()}"


async def _claim(redis: redis_asyncio.Redis, exchange: str, cut: datetime) -> bool:
    """Whether this process is the one that computes ``cut``.

    A Redis failure answers **no**: the hour is not lost (the next pass sees it
    as missing and produces it), and two producers inserting the same hour into a
    table with no unique index is the worse of the two failure modes.
    """
    try:
        return bool(await redis.set(_lock_key(exchange, cut), "1", nx=True, ex=LOCK_TTL_S))
    except Exception:
        logger.warning("scanner_regime_lock_unavailable", cut=cut.isoformat())
        return False


async def regime_hourly_loop(
    scanner: Scanner,
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
    health: RegimeHealth,
    *,
    thresholds: HourlyThresholds = DEFAULT_HOURLY_THRESHOLDS,
    days: int = BACKFILL_DAYS,
) -> None:
    """One pass per closed hour, for as long as the process lives."""
    exchange = scanner.config.exchange
    computed: datetime | None = None
    while True:
        now = utcnow()
        cut = floor_hour(now)
        refs = list(scanner.registry.by_symbol.values())
        if refs and (computed is None or cut > computed) and await _claim(redis, exchange, cut):
            computed = cut
            try:
                run = await run_regime_once(
                    factory,
                    refs,
                    now=now,
                    exchange=exchange,
                    thresholds=thresholds,
                    days=days,
                )
                health.record(run, now=now)
                runtime.mark_success()
            except asyncio.CancelledError:
                raise
            except Exception:
                runtime.mark_error()
                logger.exception("scanner_regime_pass_failed", cut=cut.isoformat())
        await asyncio.sleep(sleep_for(now, CHECK_S))


async def _run_once(exchange: str, *, days: int) -> RegimeRun:
    """One pass over the monitored universe, with a database of its own."""
    from hunter_core.db.session import create_engine, create_session_factory
    from hunter_scanner_worker.registry import MarketRegistry

    engine = create_engine(get_settings())
    try:
        factory = create_session_factory(engine)
        registry = MarketRegistry(exchange=exchange)
        await registry.refresh(factory, limit=build_config().max_markets)
        return await run_regime_once(
            factory,
            list(registry.by_symbol.values()),
            now=utcnow(),
            exchange=exchange,
            days=days,
        )
    finally:
        await engine.dispose()


def main() -> int:
    """``--once`` is required: the cadence belongs to the scanner, not to a shell.

    The output is the structured log the pass already writes
    (``scanner_regime_pass``) plus ``scanner_regime_once``: a worker package may
    not ``print`` (ruff ``T201``), and duplicating the numbers on stdout would
    give an operator two places to read one fact.
    """
    parser = argparse.ArgumentParser(description="Produce the hourly market regime rows.")
    parser.add_argument(
        "--once", action="store_true", required=True, help="run a single pass and exit"
    )
    parser.add_argument("--exchange", default=exchange_code(), help="exchange code to produce for")
    parser.add_argument(
        "--backfill-days",
        type=int,
        default=BACKFILL_DAYS,
        help="how far back missing hours are filled (default: %(default)s)",
    )
    args = parser.parse_args()
    configure_logging(get_settings(), "scanner")
    run = asyncio.run(_run_once(cast(str, args.exchange), days=cast(int, args.backfill_days)))
    logger.info(
        "scanner_regime_once",
        cut=run.cut.isoformat(),
        written=run.hours,
        last_ts=run.last_ts.isoformat() if run.last_ts else None,
        outcomes=dict(run.outcomes),
        duration_s=round(run.duration_s, 3),
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - the operator's entry point
    sys.exit(cast(Any, main()))
