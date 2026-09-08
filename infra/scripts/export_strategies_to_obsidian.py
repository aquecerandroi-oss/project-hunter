#!/usr/bin/env python3
"""Export every ``strategy_version`` to its Obsidian page — brief T3.20.

Everton, 2026-09-08: "lembra todas estrategias vao ficar no obsidian esse e o
diferencial gravar cada detalhe cada diametro". One page per version at
``obsidian/03-TRADING/Estrategias/<key>-<version>[-paper].md``, plus one family
page per ``strategies.key``. See ``obsidian/03-TRADING/Estrategias/README.md``
for the naming convention and the plantao step.

Read-only against the plain ``DATABASE_URL`` (``hunter_app``, SELECT-only) —
``strategy_versions``, ``agent_signals`` and ``system_events`` carry no
``organization_id`` (SHADOW-LAB.md, DATABASE.md §1.1), so there is no RLS to
defeat here and this script never sets ``app.current_org``.

Only the block between ``<!-- generated:start -->`` and ``<!-- generated:end
-->`` is ever written (:mod:`obsidian_marker_writer`) — hand-written notes
below it survive every run. Deterministic output (sorted keys, no timestamp
but ``updated``): two runs on the same day produce no diff.

Usage:
    uv run python infra/scripts/export_strategies_to_obsidian.py --dry-run
    uv run python infra/scripts/export_strategies_to_obsidian.py

VPS mode (the database lives there; this machine only has SSH):
    ssh hunter-vps 'docker exec hunter-api-1 python infra/scripts/export_strategies_to_obsidian.py --dry-run'
    ssh hunter-vps 'docker exec hunter-api-1 python infra/scripts/export_strategies_to_obsidian.py'
    docker cp hunter-api-1:/app/obsidian/03-TRADING/Estrategias/. ./obsidian/03-TRADING/Estrategias/
"""

from __future__ import annotations

import argparse
import asyncio
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from obsidian_family_pages import (
    FamilyEntry,
    build_family_body,
    build_family_frontmatter,
    extract_latest_result,
)
from obsidian_marker_writer import PageDiff, apply_write, plan_write
from obsidian_strategy_pages import (
    build_parameters,
    build_version_body,
    build_version_frontmatter,
    exp_links_for,
    parse_parent_version,
    parse_replication_sibling,
    sibling_slug_for,
    slug_for,
)
from obsidian_strategy_queries import fetch_cohort_counts, fetch_origin_events, fetch_version_rows
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_core.logging import get_logger
from hunter_core.settings import Settings
from hunter_core.strategies.canonical import params_hash as compute_params_hash

if TYPE_CHECKING:
    from obsidian_strategy_queries import VersionRow
    from sqlalchemy.ext.asyncio import AsyncConnection

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
ESTRATEGIAS_DIR = REPO_ROOT / "obsidian" / "03-TRADING" / "Estrategias"
EXPERIMENTS_DIR = REPO_ROOT / "obsidian" / "05-EXPERIMENTS"

_VERSION_NUMBER_RE = re.compile(r"(\d+)$")


def _version_sort_key(version: str) -> tuple[int, str]:
    """Numeric when the label ends in digits (``v2`` < ``v10``), else lexical."""
    match = _VERSION_NUMBER_RE.search(version)
    return (int(match.group(1)), version) if match else (-1, version)


def _database_url() -> str:
    secret = Settings().database_url
    if secret is None or not secret.get_secret_value():
        raise SystemExit("DATABASE_URL is not configured")
    return secret.get_secret_value()


def _read_exp_page(name: str) -> str | None:
    path = EXPERIMENTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


def _latest_verdict(exp_links: tuple[str, ...]) -> str:
    verdict = "-"
    for name in exp_links:
        text = _read_exp_page(name)
        if text is None:
            continue
        result = extract_latest_result(text)
        if result is not None:
            verdict = result
    return verdict


def _slug_of(row: VersionRow) -> str:
    """A sibling (T3.19, ``docs/plans/REPLICATION.md`` §4) is never
    ``<key>-<its own version>`` — it is named after the parent it tests."""
    sibling = parse_replication_sibling(row.changelog)
    if sibling is not None:
        parent_version, k = sibling
        return sibling_slug_for(row.strategy_key, parent_version, k)
    return slug_for(row.strategy_key, row.version, row.purpose)


def _known_siblings(row: VersionRow, versions: list[VersionRow]) -> list[tuple[int, str]]:
    """Every other row in this family whose frozen changelog names ``row`` as
    its parent, sorted by arm index — computed from rows already fetched, no
    query of its own (T3.19 writes no sibling-count column yet)."""
    found: list[tuple[int, str]] = []
    for other in versions:
        sibling = parse_replication_sibling(other.changelog)
        if sibling is not None and sibling[0] == row.version:
            found.append((sibling[1], _slug_of(other)))
    return sorted(found)


async def _version_diff(
    conn: AsyncConnection,
    row: VersionRow,
    versions: list[VersionRow],
    by_version_label: dict[str, VersionRow],
    today: date,
) -> tuple[PageDiff, FamilyEntry]:
    slug = _slug_of(row)
    parent_label = parse_parent_version(row.changelog)
    parent_row = by_version_label.get(parent_label) if parent_label else None
    derived_from_slug = _slug_of(parent_row) if parent_row else None
    siblings = _known_siblings(row, versions)
    sibling_slugs = tuple(s for _, s in siblings)
    replication_status = (
        f"{len(siblings)} irmã(s) de replicação conhecida(s) nesta árvore (T3.19) — "
        "o veredito dos quatro blocos vive no placar do Lab (T3.18), nunca duplicado aqui."
        if siblings
        else None
    )
    params = build_parameters(row.parameters_schema, row.default_parameters)
    events = await fetch_origin_events(conn, row.strategy_key, row.version)
    cohort_counts = await fetch_cohort_counts(conn, row.id)
    exp_links = exp_links_for(row.strategy_key, row.purpose)

    frontmatter = build_version_frontmatter(
        strategy_key=row.strategy_key,
        version=row.version,
        purpose=row.purpose,
        status=row.status,
        code_ref=row.code_ref,
        params_hash=compute_params_hash(row.default_parameters),
        activated_at=row.activated_at,
        deprecated_at=row.deprecated_at,
        derived_from_slug=derived_from_slug,
        cohorts=[c.cohort for c in cohort_counts],
        exp_links=exp_links,
        updated=today,
    )
    body = build_version_body(
        strategy_key=row.strategy_key,
        version=row.version,
        purpose=row.purpose,
        changelog=row.changelog,
        params=params,
        events=events,
        cohorts=cohort_counts,
        exp_links=exp_links,
        replication_status=replication_status,
        derived_from_slug=derived_from_slug,
        sibling_slugs=sibling_slugs,
    )
    title = f"{row.strategy_key} {row.version} ({row.purpose}, {row.status})"
    diff = plan_write(ESTRATEGIAS_DIR / f"{slug}.md", frontmatter, title, body)
    entry = FamilyEntry(
        version=row.version,
        purpose=row.purpose,
        status=row.status,
        slug=slug,
        verdict=_latest_verdict(exp_links),
    )
    return diff, entry


async def _build_diffs(conn: AsyncConnection, today: date) -> list[PageDiff]:
    rows = await fetch_version_rows(conn)
    by_strategy: dict[str, list[VersionRow]] = {}
    for row in rows:
        by_strategy.setdefault(row.strategy_key, []).append(row)

    diffs: list[PageDiff] = []
    for strategy_key in sorted(by_strategy):
        versions = sorted(by_strategy[strategy_key], key=lambda r: _version_sort_key(r.version))
        by_version_label = {v.version: v for v in versions}
        family_entries: list[FamilyEntry] = []
        for row in versions:
            diff, entry = await _version_diff(conn, row, versions, by_version_label, today)
            diffs.append(diff)
            family_entries.append(entry)
        family_frontmatter = build_family_frontmatter(strategy_key, today)
        family_body = build_family_body(strategy_key, family_entries)
        diffs.append(
            plan_write(
                ESTRATEGIAS_DIR / f"{strategy_key}.md",
                family_frontmatter,
                strategy_key,
                family_body,
            )
        )
    return diffs


def _print_diff(diff: PageDiff) -> None:
    if diff.action == "unchanged":
        return
    print(f"{diff.action}: {diff.path.relative_to(REPO_ROOT)}")


async def _run(*, dry_run: bool) -> int:
    engine = create_async_engine(_database_url(), connect_args={"statement_cache_size": 0})
    today = datetime.now(tz=UTC).date()
    try:
        async with engine.connect() as conn:
            diffs = await _build_diffs(conn, today)
    finally:
        await engine.dispose()

    for diff in diffs:
        _print_diff(diff)
        apply_write(diff, dry_run=dry_run)

    changed = sum(1 for d in diffs if d.action != "unchanged")
    verb = "would touch" if dry_run else "touched"
    print(f"{verb} {changed} of {len(diffs)} pages")
    logger.info("obsidian_strategy_export_done", changed=changed, total=len(diffs), dry_run=dry_run)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the diff, write nothing")
    args = parser.parse_args()
    return asyncio.run(_run(dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
