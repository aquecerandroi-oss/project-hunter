"""The per-minute cadence around :func:`run_breadth_once`, and the hand crank.

T3.77. Two entry points, one body — the shape ``beta.py`` and ``regime_hourly.py``
already use, for the same reasons:

- :func:`breadth_loop` runs inside the scanner's TaskGroup and produces the
  minute that just closed (plus any of the last three hours that have no row);
- ``python -m hunter_scanner_worker.breadth --once`` runs exactly one pass and
  exits — for a first fill, for an operator repairing a hole, and for the proof
  a task owes. Ninety days is not this crank's job: that is
  ``infra/scripts/backfill_breadth.py``, which is audited and dry-run by default.

**One producer per exchange per minute, and the lock names the minute.** The key
is ``breadth:producer:{exchange}:{cut}`` (``SET NX``, TTL 10 min, no release).
Correctness does not depend on it — ``uq_market_breadth_reading`` makes a
duplicate pass a no-op at the database — so this is economy, not integrity, and a
leader that dies mid-pass simply leaves the minute to the next pass, which sees
it as missing. That is the whole recovery story, and it is the reason the pass has
no repair rule to get wrong.

``--once`` deliberately takes no lock: an operator asking for a pass by hand has
already decided, and the pass is idempotent by key.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import TYPE_CHECKING, Any, cast

from hunter_core.domain.types import utcnow
from hunter_core.logging import configure_logging, get_logger
from hunter_core.settings import get_settings
from hunter_scanner_worker.breadth_job import (
    BACKFILL_MINUTES,
    BreadthHealth,
    BreadthRun,
    floor_minute,
    run_breadth_once,
)
from hunter_scanner_worker.config import exchange_code

if TYPE_CHECKING:
    from datetime import datetime

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime

logger = get_logger(__name__)

CHECK_S = 15.0
"""How often the loop looks at the clock. A quarter of a minute: the cut it
produces is at most a few seconds old, and a gated version whose bar closed at
``12:06`` finds its row well inside the 2 s the live path allows before it
evaluates the next bar."""

LOCK_TTL_S = 600
"""Ten minutes: far longer than a steady-state pass (one minute of the universe)
and far shorter than the interval at which stale keys would accumulate."""

__all__ = ["CHECK_S", "breadth_loop", "claim_minute", "main"]


def _lock_key(exchange: str, cut: datetime) -> str:
    return f"breadth:producer:{exchange}:{cut.isoformat()}"


async def claim_minute(redis: redis_asyncio.Redis, exchange: str, cut: datetime) -> bool:
    """Whether this process is the one that folds ``cut``.

    A Redis failure answers **no**: the minute is not lost (the next pass sees it
    as missing and produces it), and not folding twice is the cheaper mistake.
    """
    try:
        return bool(await redis.set(_lock_key(exchange, cut), "1", nx=True, ex=LOCK_TTL_S))
    except Exception:
        logger.warning("scanner_breadth_lock_unavailable", cut=cut.isoformat())
        return False


async def breadth_loop(
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
    health: BreadthHealth,
    *,
    exchange: str,
    back: int = BACKFILL_MINUTES,
) -> None:
    """One pass per closed minute, for as long as the process lives."""
    computed: datetime | None = None
    while True:
        now = utcnow()
        cut = floor_minute(now)
        if (computed is None or cut > computed) and await claim_minute(redis, exchange, cut):
            computed = cut
            try:
                run = await run_breadth_once(factory, exchange=exchange, cut=cut, back=back)
                health.last_run_at = now
                health.universe_size = run.universe_size
                if run.last_ts is not None:
                    health.last_minute = run.last_ts
                runtime.mark_success()
            except asyncio.CancelledError:
                raise
            except Exception:
                runtime.mark_error()
                logger.exception("scanner_breadth_pass_failed", cut=cut.isoformat())
        await asyncio.sleep(CHECK_S)


async def _run_once(exchange: str, *, back: int) -> BreadthRun:
    """One pass, with a database connection of its own."""
    from hunter_core.db.session import create_engine, create_session_factory

    engine = create_engine(get_settings())
    try:
        factory = create_session_factory(engine)
        return await run_breadth_once(
            factory, exchange=exchange, cut=floor_minute(utcnow()), back=back
        )
    finally:
        await engine.dispose()


def main() -> int:
    """``--once`` is required: the cadence belongs to the scanner, not to a shell.

    The output is the structured log the pass already writes
    (``scanner_breadth_pass``) plus ``scanner_breadth_once``: a worker package may
    not ``print`` (ruff ``T201``), and duplicating the numbers on stdout would give
    an operator two places to read one fact.
    """
    parser = argparse.ArgumentParser(description="Produce the per-minute breadth_5m rows.")
    parser.add_argument(
        "--once", action="store_true", required=True, help="run a single pass and exit"
    )
    parser.add_argument("--exchange", default=exchange_code(), help="exchange code to produce for")
    parser.add_argument(
        "--back-minutes",
        type=int,
        default=BACKFILL_MINUTES,
        help="how far back missing minutes are filled (default: %(default)s)",
    )
    args = parser.parse_args()
    configure_logging(get_settings(), "scanner")
    run = asyncio.run(_run_once(cast("str", args.exchange), back=cast("int", args.back_minutes)))
    logger.info(
        "scanner_breadth_once",
        cut=run.cut.isoformat(),
        universe=run.universe_size,
        due=run.due,
        written=run.written,
        outcomes=dict(run.outcomes),
        duration_s=round(run.duration_s, 3),
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - the operator's entry point
    sys.exit(cast("Any", main()))
