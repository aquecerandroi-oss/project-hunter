"""Fill ``market_breadth`` backwards — and, first, say what that fill would be worth.

T3.77 / H-P8. ``breadth_5m`` is universe-wide: unlike a per-market feature, it
cannot be backfilled for "the sixteen markets we backfilled candles for" and mean
anything. A reading is the share of the *monitored universe* that fell, so a day
on which only sixteen of two hundred perpetuals have 1-minute candles produces a
reading with 8 % coverage — which this build refuses as
``insufficient_coverage`` rather than publishing as a number.

That is why the default is not a fill but a **measurement**::

    uv run python infra/scripts/backfill_breadth.py --days 90            # coverage report
    uv run python infra/scripts/backfill_breadth.py --days 90 --plan     # + what would be written
    uv run python infra/scripts/backfill_breadth.py --days 90 --apply --reason "EXP-0027"

``--apply`` is the only mode that writes, and it writes two things in two
transactions: the readings (via the same :func:`run_breadth_once` the scanner
runs, never a second implementation) and one system-scope ``audit_logs`` row
naming who asked, for how many days, and what landed.

On the VPS this runs inside the published image, like every other audited tool::

    ./compose.sh run --rm ops python infra/scripts/backfill_breadth.py --days 90

**What this tool will not do.** It never relaxes the coverage floor and never
writes a reading for a day it could not cover: an unusable minute is stored as
unusable, with the producer's own reason, or the operator learns from the report
that the day is not worth folding at all. A number that would look like breadth
and be a fold over sixteen markets is the exact mistake ``breadth_unavailable``
exists to prevent.

**And it skips the days the report just failed** (T3.77c). ``--apply`` folds only
the minutes of days whose dense coverage reaches
:data:`~hunter_indicators.breadth.MIN_COVERAGE`; the rest are not attempted. The
reason is that a refusal *is* a write here: a minute folded over a day with no
candles lands as a ``reason = 'insufficient_coverage'`` row, and ``0019`` grants
nobody ``UPDATE`` or ``DELETE`` on ``market_breadth``, so that row is a
**permanent tombstone** for that minute in ``breadth_v1`` — never recomputable,
only superseded by a whole new ``breadth_version`` (``ddl/breadth.py``,
DATABASE.md §31). Filling ninety days of which eleven have candles would have
written ~114 000 tombstones to gain ~15 000 readings.

``--include-unusable`` folds the whole window anyway, tombstones included, for the
operator who wants the *absence* recorded as a fact rather than left as a gap. It
is a choice made in front of the report, never the default.

One boundary is worth knowing: the first five minutes of a kept day fold candles
that opened on the day before it, so when that day was skipped those few minutes
may still land as ``insufficient_coverage``. Those tombstones are measured rather
than guessed, which is the whole distinction this flag draws.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

from breadth_windows import MINUTES_PER_DAY, days_above_the_floor, fold_windows
from sqlalchemy import text

from hunter_core.db.session import create_engine, create_session_factory, role_session
from hunter_core.domain.types import utcnow, uuid7
from hunter_core.settings import get_settings
from hunter_indicators.breadth import BREADTH_VERSION, MIN_COVERAGE, WINDOW_MINUTES
from hunter_scanner_worker.breadth_job import BreadthRun, floor_minute, run_breadth_once

if TYPE_CHECKING:
    from datetime import date, datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

DB_ROLE = "hunter_worker"
MAX_DAYS = 90
"""The replay window the cohorts on disk cover. Deeper is not refused because it
is dangerous but because nothing reads it: no replay slice reaches past it."""

ACTION = "market_breadth.backfill"

_COVERAGE_SQL = text(
    "WITH universe AS ("
    "  SELECT m.id FROM markets m JOIN exchanges e ON e.id = m.exchange_id"
    "   WHERE e.code = :exchange AND m.is_monitored AND m.status = 'active'"
    "     AND m.market_type = 'perpetual'"
    "), per_day AS ("
    "  SELECT date_trunc('day', c.open_time) AS day, c.market_id, count(*) AS minutes"
    "    FROM candles c JOIN universe u ON u.id = c.market_id"
    "   WHERE c.timeframe = '1m' AND c.is_final"
    "     AND c.open_time >= :start AND c.open_time < :end"
    "   GROUP BY 1, 2"
    ") "
    "SELECT day, count(*) AS markets,"
    "       count(*) FILTER (WHERE minutes >= :dense) AS dense_markets,"
    "       sum(minutes) AS candles "
    "  FROM per_day GROUP BY day ORDER BY day"
)
"""How many monitored perpetuals have 1-minute candles on each day of the window.

``dense_markets`` counts the ones with at least ``:dense`` of the day's 1 440
minutes — a market with forty candles on a day contributes to *some* minutes and
to almost none, and counting it the same as a complete one would overstate what a
backfill could cover. Read-only, one statement, no temporary objects: safe to run
against production inside a ``READ ONLY`` transaction.
"""

_UNIVERSE_SIZE = text(
    "SELECT count(*) FROM markets m JOIN exchanges e ON e.id = m.exchange_id "
    " WHERE e.code = :exchange AND m.is_monitored AND m.status = 'active' "
    "   AND m.market_type = 'perpetual'"
)

_AUDIT = text(
    "INSERT INTO audit_logs (id, created_at, organization_id, actor_type, actor_id, action, "
    "  entity_type, entity_id, before, after, metadata) "
    "VALUES (:id, now(), NULL, 'system', NULL, :action, 'market_breadth', NULL, NULL, "
    "  CAST(:after AS jsonb), CAST(:meta AS jsonb))"
)
"""System scope (``organization_id IS NULL``): the series belongs to the exchange,
not to a tenant, and a global fill attributed to one organization would be a lie
about who it affects."""


async def _coverage(session: AsyncSession, *, exchange: str, days: int, dense: int) -> list[Any]:
    end = floor_minute(utcnow())
    rows = await session.execute(
        _COVERAGE_SQL,
        {"exchange": exchange, "start": end - timedelta(days=days), "end": end, "dense": dense},
    )
    return list(rows)


def _merge(runs: list[BreadthRun], *, cut: datetime) -> BreadthRun:
    """Several windows read as one pass, so the summary and the audit row say
    what they said when this was a single call."""
    total = BreadthRun(cut=cut)
    for one in runs:
        total.universe_size = one.universe_size
        total.due += one.due
        total.written += one.written
        total.outcomes.update(one.outcomes)
        total.last_ts = one.last_ts or total.last_ts
        total.duration_s += one.duration_s
    return total


def _print_coverage(rows: list[Any], *, universe: int, dense: int) -> set[date]:
    """Print the report and return the days a fill would actually cover."""
    floor = (MIN_COVERAGE * universe).to_integral_value(rounding="ROUND_CEILING")
    print(f"universo monitorado agora: {universe} perpétuas")
    print(f"piso de cobertura: {MIN_COVERAGE} -> {floor} mercados densos por minuto")
    print(f"denso = ao menos {dense} de 1440 velas de 1 min no dia")
    print("")
    print(f"{'dia':<12}{'mercados':>10}{'densos':>10}{'cobertura':>12}{'velas':>12}")
    above = days_above_the_floor(rows, universe=universe)
    for row in rows:
        coverage = 0.0 if universe <= 0 else row.dense_markets / universe
        print(
            f"{row.day.date().isoformat():<12}{row.markets:>10}{row.dense_markets:>10}"
            f"{coverage:>11.1%}{int(row.candles):>12}"
        )
    print("")
    print(f"dias que passariam o piso de cobertura: {len(above)} de {len(rows)}")
    return above


async def _write_audit(
    factory: async_sessionmaker[AsyncSession],
    *,
    exchange: str,
    days: int,
    reason: str,
    run: BreadthRun,
    windows: list[tuple[datetime, int]],
    include_unusable: bool,
) -> None:
    import json

    async with role_session(factory, db_role=DB_ROLE) as session:
        await session.execute(
            _AUDIT,
            {
                "id": uuid7(),
                "action": ACTION,
                "after": json.dumps(
                    {
                        "exchange": exchange,
                        "days": days,
                        "cut": run.cut.isoformat(),
                        "due": run.due,
                        "written": run.written,
                        "universe_size": run.universe_size,
                        "outcomes": dict(run.outcomes),
                        "windows": [
                            {"cut": window.isoformat(), "back": back} for window, back in windows
                        ],
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                "meta": json.dumps(
                    {
                        "reason": reason,
                        "include_unusable": include_unusable,
                        "breadth_version": BREADTH_VERSION,
                        "window_minutes": WINDOW_MINUTES,
                        "tool": "infra/scripts/backfill_breadth.py",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            },
        )


def _summarise(run: BreadthRun, *, applied: bool, windows: int) -> None:
    print("")
    print(f"corte: {run.cut.isoformat()}  universo: {run.universe_size}")
    print(f"janelas dobradas: {windows}")
    print(f"minutos sem linha na janela: {run.due}")
    for outcome, count in sorted(run.outcomes.items()):
        print(f"  {outcome}: {count}")
    print(f"linhas gravadas: {run.written}" if applied else "[dry-run] nada foi gravado")
    print(f"duração: {run.duration_s:.1f} s")


async def _run(args: argparse.Namespace) -> int:
    days = cast("int", args.days)
    if not 1 <= days <= MAX_DAYS:
        print(f"RECUSADO: --days {days} fora de 1-{MAX_DAYS}", file=sys.stderr)
        return 1
    apply_it = bool(args.apply)
    if apply_it and not cast("str", args.reason or "").strip():
        print("RECUSADO: --apply exige --reason (vai para audit_logs)", file=sys.stderr)
        return 1
    exchange = cast("str", args.exchange)
    engine = create_engine(get_settings())
    try:
        factory = create_session_factory(engine)
        async with role_session(factory, db_role=DB_ROLE) as session:
            universe = await session.scalar(_UNIVERSE_SIZE, {"exchange": exchange}) or 0
            rows = await _coverage(
                session, exchange=exchange, days=days, dense=cast("int", args.dense)
            )
        above = _print_coverage(rows, universe=universe, dense=cast("int", args.dense))
        if not (apply_it or args.plan):
            return 0
        include_unusable = bool(args.include_unusable)
        cut = floor_minute(utcnow())
        windows = fold_windows(cut, days=days, keep=None if include_unusable else above)
        skipped = days - sum(back for _, back in windows) // MINUTES_PER_DAY
        if not windows:
            print(
                "RECUSADO: nenhum dia da janela alcança o piso de cobertura. Gravar assim "
                "mesmo é --include-unusable, e são lápides permanentes em "
                f"{BREADTH_VERSION}",
                file=sys.stderr,
            )
            return 1
        print(f"dias fora do piso, não dobrados: ~{max(skipped, 0)} (--include-unusable os inclui)")
        run = _merge(
            [
                await run_breadth_once(
                    factory,
                    exchange=exchange,
                    cut=window,
                    back=back,
                    dry_run=not apply_it,
                )
                for window, back in windows
            ],
            cut=cut,
        )
        _summarise(run, applied=apply_it, windows=len(windows))
        if apply_it:
            await _write_audit(
                factory,
                exchange=exchange,
                days=days,
                reason=cast("str", args.reason),
                run=run,
                windows=windows,
                include_unusable=include_unusable,
            )
            print(f"audit_logs: uma linha {ACTION} gravada")
    finally:
        await engine.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exchange", default="binance", help="código da exchange")
    parser.add_argument(
        "--days", type=int, default=MAX_DAYS, help="janela para trás (padrão: %(default)s)"
    )
    parser.add_argument(
        "--dense",
        type=int,
        default=1_200,
        help="velas de 1 min mínimas no dia para o mercado contar como denso",
    )
    parser.add_argument(
        "--plan", action="store_true", help="além do relatório, dobre a janela sem gravar"
    )
    parser.add_argument("--apply", action="store_true", help="grave as leituras (padrão: não)")
    parser.add_argument(
        "--include-unusable",
        action="store_true",
        help="dobre também os dias abaixo do piso; grava lápides permanentes",
    )
    parser.add_argument("--reason", help="por que este backfill; obrigatório com --apply")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":  # pragma: no cover - the operator's entry point
    sys.exit(main())
