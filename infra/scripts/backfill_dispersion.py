"""Fill ``market_dispersion`` backwards — and, first, say what that fill is worth.

T3.90 / H-P18, on the shape ``backfill_breadth.py`` has after T3.88::

    uv run python infra/scripts/backfill_dispersion.py --days 90            # report
    uv run python infra/scripts/backfill_dispersion.py --days 90 --plan     # + fold, no write
    uv run python infra/scripts/backfill_dispersion.py --days 90 --apply --reason "EXP-0029"

``--apply`` is the only mode that writes, and it writes two things in two
transactions: the readings (via the same :func:`run_dispersion_once` the scanner
runs, never a second implementation) and one system-scope ``audit_logs`` row naming
who asked, for how many days, on which series, and what landed.

On the VPS this runs inside the published image, like every other audited tool::

    ./compose.sh run --rm ops python infra/scripts/backfill_dispersion.py --days 90

**One universe for the whole span.** Membership is resolved once, at the top cut,
and every minute of the ninety days is folded over that one list
(``run_dispersion_once(universe_as_of=...)``). Asking again per chunk would let the
series change universe halfway through; asking at each historical minute would
answer "nobody", since no market had ninety days of retained candles ninety days
ago. ``market_dispersion.universe_size`` documents itself as evidence about the fold
rather than about the historical minute, and this is that sentence made executable.

**Why this tool can measure ninety days at all, where ``breadth_v1`` could not.**
``breadth_v1`` was a fraction of ~200 monitored perpetuals and 87 of 91 days were
``insufficient_coverage`` (VPS, 2026-09-10). This series starts where T3.88 ended:
its first version's universe is the sixteen markets with 90 days of 1m candles — the
shadow universe, and the population every replay cohort is drawn from.

**What this tool will not do.** It never relaxes the coverage floor and never folds a
day the report failed: a refusal *is* a write here, and ``0020`` grants nobody
``UPDATE`` or ``DELETE``, so the row is a permanent tombstone for that minute in that
series. Three rules decide what is folded (``dispersion_windows``): the day clears
the floor, **the day before it clears the floor** (at a 24 h horizon every minute
reaches into the previous day — so a kept day after a skipped one would be 1 440
tombstones), and the **reference market** is dense on both. ``--days 90`` therefore
folds at most 89 days: the oldest day of the report has no predecessor in it.

``--include-unusable`` folds the whole window anyway, tombstones included, for the
operator who wants the *absence* recorded as a fact rather than left as a gap. A
choice made in front of the report, never the default.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import TYPE_CHECKING, cast

from breadth_coverage import day_coverage
from breadth_windows import MINUTES_PER_DAY, fold_windows
from dispersion_windows import days_above_the_floor, foldable_days
from sqlalchemy import text

from hunter_core.db.session import create_engine, create_session_factory, role_session
from hunter_core.domain.types import utcnow, uuid7
from hunter_core.settings import get_settings
from hunter_indicators.dispersion import CURRENT_DISPERSION_VERSION, SPECS, spec_for
from hunter_scanner_worker.dispersion_job import (
    DispersionRun,
    floor_minute,
    run_dispersion_once,
)
from hunter_scanner_worker.dispersion_repo import universe_members

if TYPE_CHECKING:
    from datetime import date, datetime
    from uuid import UUID

    from breadth_coverage import CoverageRow
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.universe import UniverseMember
    from hunter_indicators.dispersion import DispersionSpec

DB_ROLE = "hunter_worker"
MAX_DAYS = 90
"""The replay window the cohorts on disk cover. Deeper is not refused because it is
dangerous but because nothing reads it: no replay slice reaches past it."""

ACTION = "market_dispersion.backfill"

_AUDIT = text(
    "INSERT INTO audit_logs (id, created_at, organization_id, actor_type, actor_id, action, "
    "  entity_type, entity_id, before, after, metadata) "
    "VALUES (:id, now(), NULL, 'system', NULL, :action, 'market_dispersion', NULL, NULL, "
    "  CAST(:after AS jsonb), CAST(:meta AS jsonb))"
)
"""System scope (``organization_id IS NULL``): the series belongs to the exchange,
not to a tenant, and a global fill attributed to one organization would be a lie
about who it affects."""


def _merge(runs: list[DispersionRun], *, cut: datetime) -> DispersionRun:
    """Several windows read as one pass, so the summary and the audit row say what
    they would say if this were a single call."""
    total = DispersionRun(cut=cut)
    for one in runs:
        total.universe_size = one.universe_size
        total.reference_found = one.reference_found
        total.due += one.due
        total.written += one.written
        total.outcomes.update(one.outcomes)
        total.last_ts = one.last_ts or total.last_ts
        total.duration_s += one.duration_s
    return total


def _print_report(
    rows: list[CoverageRow],
    *,
    universe: int,
    dense: int,
    spec: DispersionSpec,
    reference: UUID | None,
    above: set[date],
    keep: set[date],
) -> None:
    """The measurement, day by day, and the two verdicts it produces."""
    floor = (spec.min_coverage * universe).to_integral_value(rounding="ROUND_CEILING")
    print(f"série: {spec.version}  universo: {spec.universe_rule}")
    print(f"universo agora: {universe} perpétuas")
    print(f"referência: {spec.reference_symbol} ({'no universo' if reference else 'AUSENTE'})")
    print(f"horizonte: {spec.horizon_minutes} min")
    print(f"piso de cobertura: {spec.min_coverage} -> {floor} mercados densos por minuto")
    print(f"denso = ao menos {dense} de 1440 velas de 1 min no dia")
    print("")
    print(f"{'dia':<12}{'mercados':>10}{'densos':>10}{'cobertura':>12}{'velas':>12}{'dobra':>8}")
    for row in rows:
        coverage = 0.0 if universe <= 0 else row.dense_markets / universe
        mark = "sim" if row.day.date() in keep else "-"
        print(
            f"{row.day.date().isoformat():<12}{row.markets:>10}{row.dense_markets:>10}"
            f"{coverage:>11.1%}{row.candles:>12}{mark:>8}"
        )
    print("")
    print(f"dias que passam o piso de cobertura: {len(above)} de {len(rows)}")
    print(f"dias dobráveis (piso + véspera coberta + referência densa nos dois): {len(keep)}")


async def _measure(
    session: AsyncSession,
    *,
    exchange: str,
    spec: DispersionSpec,
    cut: datetime,
    days: int,
    dense: int,
) -> tuple[tuple[UniverseMember, ...], UUID | None, list[CoverageRow], list[CoverageRow]]:
    """The universe, the reference, the universe's per-day coverage and the
    reference's own — four reads, no writes, nothing interpreted."""
    members = await universe_members(
        session, exchange=exchange, min_history_days=spec.min_history_days, clock=lambda: cut
    )
    reference = next(
        (member.market_id for member in members if member.symbol == spec.reference_symbol), None
    )
    ids = [member.market_id for member in members]
    rows = await day_coverage(session, market_ids=ids, days=days, end=cut, dense=dense)
    reference_rows = (
        []
        if reference is None
        else await day_coverage(session, market_ids=[reference], days=days, end=cut, dense=dense)
    )
    return members, reference, rows, reference_rows


async def _write_audit(
    factory: async_sessionmaker[AsyncSession],
    *,
    exchange: str,
    days: int,
    reason: str,
    run: DispersionRun,
    windows: list[tuple[datetime, int]],
    include_unusable: bool,
    spec: DispersionSpec,
) -> None:
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
                        "reference_found": run.reference_found,
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
                        "dispersion_version": spec.version,
                        "universe_rule": spec.universe_rule,
                        "min_history_days": spec.min_history_days,
                        "horizon_minutes": spec.horizon_minutes,
                        "reference_symbol": spec.reference_symbol,
                        "tool": "infra/scripts/backfill_dispersion.py",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            },
        )


def _summarise(run: DispersionRun, *, applied: bool, windows: int, spec: DispersionSpec) -> None:
    print("")
    print(f"série: {spec.version}  corte: {run.cut.isoformat()}  universo: {run.universe_size}")
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
    spec = spec_for(cast("str", args.series))
    exchange = cast("str", args.exchange)
    dense = cast("int", args.dense)
    engine = create_engine(get_settings())
    try:
        factory = create_session_factory(engine)
        cut = floor_minute(utcnow())
        async with role_session(factory, db_role=DB_ROLE) as session:
            members, reference, rows, reference_rows = await _measure(
                session, exchange=exchange, spec=spec, cut=cut, days=days, dense=dense
            )
        above = days_above_the_floor(rows, universe=len(members), floor=spec.min_coverage)
        keep = foldable_days(
            above, reference_days={row.day.date() for row in reference_rows if row.dense_markets}
        )
        _print_report(
            rows,
            universe=len(members),
            dense=dense,
            spec=spec,
            reference=reference,
            above=above,
            keep=keep,
        )
        if not (apply_it or args.plan):
            return 0
        include_unusable = bool(args.include_unusable)
        windows = fold_windows(cut, days=days, keep=None if include_unusable else keep)
        if not windows:
            print(
                "RECUSADO: nenhum dia da janela é dobrável (piso, véspera coberta e referência "
                f"densa). Gravar assim mesmo é --include-unusable, e são lápides permanentes em "
                f"{spec.version}",
                file=sys.stderr,
            )
            return 1
        skipped = days - sum(back for _, back in windows) // MINUTES_PER_DAY
        print(f"dias não dobrados: ~{max(skipped, 0)} (--include-unusable os inclui)")
        run = _merge(
            [
                await run_dispersion_once(
                    factory,
                    exchange=exchange,
                    cut=window,
                    back=back,
                    spec=spec,
                    universe_as_of=cut,
                    dry_run=not apply_it,
                )
                for window, back in windows
            ],
            cut=cut,
        )
        _summarise(run, applied=apply_it, windows=len(windows), spec=spec)
        if apply_it:
            await _write_audit(
                factory,
                exchange=exchange,
                days=days,
                reason=cast("str", args.reason),
                run=run,
                windows=windows,
                include_unusable=include_unusable,
                spec=spec,
            )
            print(f"audit_logs: uma linha {ACTION} gravada")
    finally:
        await engine.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exchange", default="binance", help="código da exchange")
    parser.add_argument(
        "--series",
        default=CURRENT_DISPERSION_VERSION,
        choices=sorted(SPECS),
        help="qual série dobrar (padrão: %(default)s)",
    )
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
        help="dobre também os dias não dobráveis; grava lápides permanentes",
    )
    parser.add_argument("--reason", help="por que este backfill; obrigatório com --apply")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":  # pragma: no cover - the operator's entry point
    sys.exit(main())
