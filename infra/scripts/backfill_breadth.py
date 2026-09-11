"""Fill ``market_breadth`` backwards — and, first, say what that fill would be worth.

T3.77 / H-P8, rewritten by T3.88. ``breadth_5m`` is universe-wide: unlike a
per-market feature it cannot be backfilled for "the sixteen markets we backfilled
candles for" and mean anything *as v1*, because a v1 reading is the share of ~200
monitored perpetuals that fell and a day on which only sixteen of them have
1-minute candles is 8 % coverage — refused as ``insufficient_coverage``, which is
why 87 of the last 91 days were unfoldable and EXP-0027 was prospective-only.

**T3.88's answer is a different series, not a relaxed floor.** ``breadth_v2``
declares the universe to be the sixteen markets with 90 days of 1-minute history
— the shadow universe (T3.82), and the only population any replay cohort is drawn
from. The floor stays at 80 % and now it is 80 % of *that* universe, so the same
ninety days are measurable. ``breadth_v1`` rows are never rewritten: a different
universe is a different series, and ``--series breadth_v1`` still reproduces the
old one::

    uv run python infra/scripts/backfill_breadth.py --days 90            # coverage report
    uv run python infra/scripts/backfill_breadth.py --days 90 --plan     # + what would be written
    uv run python infra/scripts/backfill_breadth.py --days 90 --apply --reason "EXP-0027"

``--apply`` is the only mode that writes, and it writes two things in two
transactions: the readings (via the same :func:`run_breadth_once` the scanner
runs, never a second implementation) and one system-scope ``audit_logs`` row
naming who asked, for how many days, on which series, and what landed.

On the VPS this runs inside the published image, like every other audited tool::

    ./compose.sh run --rm ops python infra/scripts/backfill_breadth.py --days 90

**One universe for the whole span.** Membership is resolved once, at the top cut,
and every minute of the ninety days is folded over that one list
(``run_breadth_once(universe_as_of=...)``). Asking the question again per chunk
would let the series change universe halfway through; asking it at each historical
minute would answer "nobody", since no market had ninety days of retained candles
ninety days ago. ``market_breadth.universe_size`` has always documented itself as
evidence about the fold rather than about the historical minute, and this is that
sentence made executable.

**What this tool will not do.** It never relaxes the coverage floor and never
writes a reading for a day it could not cover: an unusable minute is stored as
unusable, with the producer's own reason, or the operator learns from the report
that the day is not worth folding at all.

**And it skips the days the report just failed** (T3.77c). ``--apply`` folds only
the minutes of days whose dense coverage reaches the series' floor; the rest are
not attempted. The reason is that a refusal *is* a write here: a minute folded
over a day with no candles lands as a ``reason = 'insufficient_coverage'`` row,
and ``0019`` grants nobody ``UPDATE`` or ``DELETE`` on ``market_breadth``, so that
row is a **permanent tombstone** for that minute in that series — never
recomputable, only superseded by a whole new ``breadth_version``
(``ddl/breadth.py``, DATABASE.md §31).

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
from typing import TYPE_CHECKING, cast

from breadth_coverage import day_coverage, print_coverage, universe_ids
from breadth_windows import MINUTES_PER_DAY, fold_windows
from sqlalchemy import text

from hunter_core.db.session import create_engine, create_session_factory, role_session
from hunter_core.domain.types import utcnow, uuid7
from hunter_core.settings import get_settings
from hunter_indicators.breadth import CURRENT_BREADTH_VERSION, SPECS, spec_for
from hunter_scanner_worker.breadth_job import BreadthRun, floor_minute, run_breadth_once

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_indicators.breadth import BreadthSpec

DB_ROLE = "hunter_worker"
MAX_DAYS = 90
"""The replay window the cohorts on disk cover. Deeper is not refused because it
is dangerous but because nothing reads it: no replay slice reaches past it."""

ACTION = "market_breadth.backfill"

_AUDIT = text(
    "INSERT INTO audit_logs (id, created_at, organization_id, actor_type, actor_id, action, "
    "  entity_type, entity_id, before, after, metadata) "
    "VALUES (:id, now(), NULL, 'system', NULL, :action, 'market_breadth', NULL, NULL, "
    "  CAST(:after AS jsonb), CAST(:meta AS jsonb))"
)
"""System scope (``organization_id IS NULL``): the series belongs to the exchange,
not to a tenant, and a global fill attributed to one organization would be a lie
about who it affects."""


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


async def _write_audit(
    factory: async_sessionmaker[AsyncSession],
    *,
    exchange: str,
    days: int,
    reason: str,
    run: BreadthRun,
    windows: list[tuple[datetime, int]],
    include_unusable: bool,
    spec: BreadthSpec,
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
                        "breadth_version": spec.version,
                        "universe_rule": spec.universe_rule,
                        "min_history_days": spec.min_history_days,
                        "window_minutes": spec.window_minutes,
                        "tool": "infra/scripts/backfill_breadth.py",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            },
        )


def _summarise(run: BreadthRun, *, applied: bool, windows: int, spec: BreadthSpec) -> None:
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
            ids = await universe_ids(session, exchange=exchange, spec=spec, as_of=cut)
            rows = await day_coverage(session, market_ids=ids, days=days, end=cut, dense=dense)
        above = print_coverage(rows, universe=len(ids), dense=dense, spec=spec)
        if not (apply_it or args.plan):
            return 0
        include_unusable = bool(args.include_unusable)
        windows = fold_windows(cut, days=days, keep=None if include_unusable else above)
        skipped = days - sum(back for _, back in windows) // MINUTES_PER_DAY
        if not windows:
            print(
                "RECUSADO: nenhum dia da janela alcança o piso de cobertura. Gravar assim "
                f"mesmo é --include-unusable, e são lápides permanentes em {spec.version}",
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
        default=CURRENT_BREADTH_VERSION,
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
        help="dobre também os dias abaixo do piso; grava lápides permanentes",
    )
    parser.add_argument("--reason", help="por que este backfill; obrigatório com --apply")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":  # pragma: no cover - the operator's entry point
    sys.exit(main())
