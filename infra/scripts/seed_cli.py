"""``uv run python infra/scripts/seed.py [--dry-run] [--only <table>] [--yes]`` (T3.39).

Split out of ``seed.py`` for the 350-line budget, the way ``seed_paper.py`` and
``seed_weights.py`` already were. Composes the very functions ``seed()``
already calls — nothing here re-implements a table's upsert — around three
operator-facing needs the plain ``seed()`` did not have:

- ``--dry-run``: run every writer the invocation would run, print the diff,
  then roll the transaction back. The counts and the diff are both real (read
  from ``RETURNING``/the database mid-transaction); only the commit never
  happens.
- ``--only <table>``: restrict the run to one table's own transaction —
  ``strategies``, ``risk_profiles``, ``feature_definitions`` or
  ``opportunity_weights`` (:data:`seed_dry_run.TABLE_CHOICES`). ``strategies``
  and ``strategy_versions`` move together (one upsert, two report keys);
  ``risk_profiles`` and ``paper_v1`` move together the same way ``seed()``
  already does.
- the risk directive: a write that would change a stored ``risk_profiles``
  limit — any of the three presets or ``paper_v1`` — refuses before it commits
  unless ``--yes`` is given. "Limits are never changed without being presented
  first" (``.claude/state/directive-risk-engine-2026-09-06.md``); ``--dry-run``
  is how they get presented.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable

import seed_dry_run
from seed import (
    migration_url,
    seed_exchanges,
    seed_feature_definitions,
    seed_feature_flags,
    seed_paper_preset,
    seed_plan_entitlements,
    seed_risk_profiles,
    seed_strategies,
)
from seed_weights import seed_opportunity_weights
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

_RISK_DIRECTIVE = (
    "Everton's directive: a limit is never changed without being presented first "
    "(.claude/state/directive-risk-engine-2026-09-06.md). Run --dry-run to see the diff, or "
    "re-run with --yes once it has been."
)

_UNATTENDED_DIRECTIVE = (
    "stdin is not a TTY (a piped or scripted invocation, e.g. `docker exec -i ... python -`), "
    "and nobody is watching this diff scroll by: re-run with --yes once it has been reviewed, "
    "or --dry-run to only preview it (T3.39b review, MÉDIA-4 — a write is never silent in a pipe)."
)


async def _seed_risk_profiles_table(conn: AsyncConnection) -> int:
    """Both writers of the ``risk_profiles`` table, together — the report's one key."""
    return await seed_risk_profiles(conn) + await seed_paper_preset(conn)


async def _run_only(conn: AsyncConnection, only: str) -> dict[str, int]:
    if only == "strategies":
        strategies, versions = await seed_strategies(conn)
        return {"strategies": strategies, "strategy_versions": versions}
    if only == "risk_profiles":
        return {"risk_profiles": await _seed_risk_profiles_table(conn)}
    if only == "feature_definitions":
        return {"feature_definitions": await seed_feature_definitions(conn)}
    return {"opportunity_weights": await seed_opportunity_weights(conn)}


async def _run_everything(conn: AsyncConnection) -> dict[str, int]:
    exchanges = await seed_exchanges(conn)
    strategies, versions = await seed_strategies(conn)
    return {
        "exchanges": exchanges,
        "strategies": strategies,
        "strategy_versions": versions,
        "plan_entitlements": await seed_plan_entitlements(conn),
        "feature_flags": await seed_feature_flags(conn),
        "risk_profiles": await _seed_risk_profiles_table(conn),
        "feature_definitions": await seed_feature_definitions(conn),
        "opportunity_weights": await seed_opportunity_weights(conn),
    }


async def seed_with_report(
    *,
    dry_run: bool = False,
    only: str | None = None,
    yes: bool = False,
    attended: bool = True,
    emit: Callable[[str], None] = print,
) -> tuple[dict[str, int], list[str]]:
    """Seed (or preview) the reference tables. Returns ``(counts, diff_lines)``.

    One open transaction for the whole call, committed only at the very end:
    ``dry_run`` rolls it back regardless of what ran, and a refusal — the risk
    directive or the unattended gate below — rolls back whatever this same
    call already wrote. A refused run never leaves a partial write behind.

    ``attended`` is ``main()``'s ``sys.stdin.isatty()`` at the moment it was
    invoked (T3.39b review, MÉDIA-4): a caller at a real keyboard sees the diff
    ``emit`` just printed before the write lands; a caller through a pipe (the
    VPS runbooks' ``docker exec -i ... python -``) never gets a second chance
    to look, so a non-empty diff refuses there without ``--yes``. Defaulting to
    ``True`` keeps every direct caller of this function (tests, other code)
    unaffected — only ``main()`` measures the real terminal and passes the
    answer down.
    """
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            before = await seed_dry_run.snapshot(conn, only)
            if not dry_run and only in (None, "risk_profiles"):
                changing = await seed_dry_run.risk_profiles_would_change(conn)
                if changing and not yes:
                    await trans.rollback()
                    raise SystemExit(
                        f"risk_profiles limits would change for {', '.join(changing)}: "
                        + _RISK_DIRECTIVE
                    )
            counts = await (_run_only(conn, only) if only is not None else _run_everything(conn))
            after = await seed_dry_run.snapshot(conn, only)
            diff = seed_dry_run.diff_lines(before, after)
            for line in diff:
                emit(line)
            if diff and not dry_run and not yes and not attended:
                await trans.rollback()
                raise SystemExit(f"seed would change stored rows and {_UNATTENDED_DIRECTIVE}")
            if dry_run:
                await trans.rollback()
            else:
                await trans.commit()
            return counts, diff
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the diff, write nothing")
    parser.add_argument(
        "--only",
        choices=seed_dry_run.TABLE_CHOICES,
        default=None,
        help="seed only this table, in its own transaction",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm a risk_profiles limits change (Everton's directive: never silent)",
    )
    args = parser.parse_args()
    counts, _diff = asyncio.run(
        seed_with_report(
            dry_run=args.dry_run,
            only=args.only,
            yes=args.yes,
            attended=sys.stdin.isatty(),
        )
    )
    if args.dry_run:
        print("DRY RUN: nothing written")
        return 0
    for table, count in counts.items():
        print(f"seeded {count:>3} row(s) into {table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
