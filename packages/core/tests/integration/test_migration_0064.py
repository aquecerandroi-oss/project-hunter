"""``0064_meme_tokens_symbol_index`` (24/09/2026 incident) — its own file and its
own database, ``test_migration_0063.py``'s shape; the one line this revision
owes ``test_migrations.py`` (``HEAD_REVISION``) is changed there too.

What is proved, on ~20 000 tokens inside 24 h (4 per ticker, the shape the VPS
measured — 32 687 rows of the window discarded per judged mint without the
index): the index is built **valid**, on ``(symbol, created_at)`` with the
partial predicate; ``lab_repo_fast.pedigree_for`` returns **the same four
counts** for every judged mint before the revision, after it, after its
downgrade and after the re-upgrade (the SQL is untouched — only the plan may
change); the plan of ``symbol_dup_24h`` reads the new index; the downgrade
removes it; and rerunning the revision over an ``indisvalid = false`` leftover
of the same name (a crashed ``CONCURRENTLY`` build) rebuilds the right one — the recovery the
revision promises.

Anything that drives Alembic is a **sync** test: ``env.py`` calls
``asyncio.run``, which raises inside a running event loop.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, cast

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from hunter_meme_worker.lab_repo_fast import (
    _PEDIGREE,  # pyright: ignore[reportPrivateUsage]
    PRIOR_WINDOW_S,
    pedigree_for,
)

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database

pytestmark = pytest.mark.integration

REVISION = "0064_meme_tokens_symbol_index"
PREVIOUS = "0063_meme_pullback_entry_arm"
INDEX = "ix_meme_tokens_symbol_created_at"

TOKENS = 20_000
JUDGED = [f"M64_{i:05d}" for i in range(0, TOKENS, 97)]
"""~206 judged mints spread over the whole window — about one in five lands on a
NULL-symbol (``i % 7 = 3``) or NULL-created_at (``i % 11 = 5``) row below, so the
``NULL`` branches are compared too, not only the counts."""

_PLANT = text(
    "INSERT INTO meme_tokens (mint, symbol, creator, created_at, first_seen_source, "
    "  first_seen_at, last_seen_at) "
    "SELECT 'M64_' || lpad(i::text, 5, '0'), "
    "       CASE WHEN i % 7 = 3 THEN NULL ELSE 'T' || (i % 5000) END, "
    "       'C' || (i % 1500), "
    "       CASE WHEN i % 11 = 5 THEN NULL "
    "            ELSE timestamptz '2026-09-24 12:00Z' - make_interval(secs => i * 4.1) END, "
    "       'pumpportal_ws', now(), now() "
    "FROM generate_series(0, :n - 1) AS i"
)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    url = _run(create_database(container_url, "hunter_migration_0064"))
    command.upgrade(alembic_config(url), PREVIOUS)
    _run(_execute(url, _PLANT, {"n": TOKENS}))
    _run(_execute(url, text("ANALYZE meme_tokens"), {}))
    return url


async def _execute(url: str, statement: Any, params: dict[str, Any]) -> None:
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(statement, params)
    finally:
        await engine.dispose()


async def _pedigree(url: str) -> dict[str, tuple[int | None, ...]]:
    engine = async_engine(url)
    try:
        async with AsyncSession(engine) as session:
            read = await pedigree_for(session, JUDGED)
    finally:
        await engine.dispose()
    return {
        mint: (
            f.creator_prior_mints_1h,
            f.symbol_dup_24h,
            f.creator_prior_dump_count,
            f.creator_prior_dead_count,
        )
        for mint, f in read.items()
    }


async def _index(url: str) -> tuple[bool, str] | None:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT i.indisvalid, pg_get_indexdef(i.indexrelid) FROM pg_index i "
                        "JOIN pg_class c ON c.oid = i.indexrelid WHERE c.relname = :name"
                    ),
                    {"name": INDEX},
                )
            ).one_or_none()
    finally:
        await engine.dispose()
    return None if row is None else (bool(row[0]), str(row[1]))


async def _symbol_subplan_indexes(url: str) -> set[str]:
    """Every index the plan of ``symbol_dup_24h``'s subquery reads — found by the
    one filter only that subquery has (``symbol = t.symbol``)."""
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            plan = await connection.scalar(
                text(f"EXPLAIN (FORMAT JSON) {_PEDIGREE.text}"),
                {
                    "mints": JUDGED,
                    "creator_window_s": 3600,
                    "symbol_window_s": 86400,
                    "prior_window_s": PRIOR_WINDOW_S,
                    "probe_rule_set_id": "01994d00-6c1a-7000-8000-00000000001c",
                    "pullback_rule_set_id": "01994d00-6c1a-7000-8000-00000000001d",
                },
            )
    finally:
        await engine.dispose()
    found: set[str] = set()

    def walk(node: dict[str, Any]) -> None:
        conditions = f"{node.get('Index Cond', '')} {node.get('Filter', '')}"
        if "symbol = t.symbol" in conditions and "Index Name" in node:
            found.add(node["Index Name"])
        for child in node.get("Plans", []):
            walk(child)

    document = cast(
        "list[dict[str, Any]]", plan if isinstance(plan, list) else json.loads(str(plan))
    )
    walk(document[0]["Plan"])
    return found


def test_the_revision_lands_on_0063_and_fits_the_version_column() -> None:
    source = (REPO_ROOT / "infra" / "migrations" / "versions" / f"{REVISION}.py").read_text(
        encoding="utf-8"
    )
    assert f'revision: str = "{REVISION}"' in source
    assert f'down_revision: str | None = "{PREVIOUS}"' in source
    assert len(REVISION) <= 32


def test_the_index_changes_the_plan_and_never_the_counts(db_url: str) -> None:
    config = alembic_config(db_url)
    before = _run(_pedigree(db_url))
    assert len(before) == len(JUDGED)
    assert any(v[1] is None for v in before.values()), "the NULL branch is compared too"
    assert any((v[1] or 0) > 0 for v in before.values()), "and real clones, not only zeros"
    assert _run(_index(db_url)) is None
    assert INDEX not in _run(_symbol_subplan_indexes(db_url))

    command.upgrade(config, REVISION)
    valid, definition = _run(_index(db_url))
    assert valid, "a CONCURRENTLY build can leave indisvalid = false behind"
    assert "(symbol, created_at)" in definition
    assert "WHERE ((symbol IS NOT NULL) AND (created_at IS NOT NULL))" in definition
    assert _run(_symbol_subplan_indexes(db_url)) == {INDEX}
    assert _run(_pedigree(db_url)) == before

    command.downgrade(config, PREVIOUS)
    assert _run(_index(db_url)) is None
    assert _run(_pedigree(db_url)) == before

    command.upgrade(config, REVISION)
    assert _run(_index(db_url)) is not None
    assert _run(_pedigree(db_url)) == before


async def _leave_an_invalid_index_behind(url: str) -> None:
    """A real crashed ``CONCURRENTLY`` build: a UNIQUE build over the duplicated
    tickers fails *after* the catalog entry exists, leaving ``indisvalid = false``
    under the final name — what ``CREATE INDEX IF NOT EXISTS`` would keep."""
    engine = async_engine(url).execution_options(isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            with pytest.raises(DBAPIError):
                await connection.execute(
                    text(f"CREATE UNIQUE INDEX CONCURRENTLY {INDEX} ON meme_tokens (symbol)")
                )
    finally:
        await engine.dispose()


def test_rerunning_over_an_invalid_leftover_of_the_same_name_rebuilds_the_right_index(
    db_url: str,
) -> None:
    config = alembic_config(db_url)
    command.downgrade(config, PREVIOUS)
    _run(_leave_an_invalid_index_behind(db_url))
    leftover = _run(_index(db_url))
    assert leftover is not None and not leftover[0], leftover
    command.upgrade(config, REVISION)
    valid, definition = _run(_index(db_url))
    assert valid and "(symbol, created_at)" in definition, definition


def test_a_longer_downgrade_that_fails_further_down_keeps_the_index(db_url: str) -> None:
    """The whole run is one transaction (``env.py``): when ``0059``'s guard
    refuses a downgrade that started at this revision, the drop must roll back
    with it. A ``DROP INDEX CONCURRENTLY`` in an ``autocommit_block`` had
    already committed — the database said ``0064`` with no index behind it, and
    ``alembic check`` failed (``test_migrations.py::test_0059_refuses_…``)."""
    config = alembic_config(db_url)
    command.upgrade(config, REVISION)
    headline = text(
        "INSERT INTO market_events (id, symbol, source, kind, title, url, observed_at, "
        "  confidence, recorded_by) VALUES ('00000000-0000-4000-8000-000000006401', "
        "  'ZECUSDT', 'baha', 'listing', 'T0064 guard', 'https://example.test/0064', now(), "
        "  'reported', 'test')"
    )
    _run(_execute(db_url, headline, {}))
    try:
        with pytest.raises(DBAPIError, match="market_events rows were recorded by hand"):
            command.downgrade(config, "0058_meme_gate_absorb_arm")
        valid, _definition = _run(_index(db_url))
        assert valid, "the drop rolled back with the refused downgrade"
        command.check(config)
    finally:
        cleanup = text("DELETE FROM market_events WHERE url = 'https://example.test/0064'")
        _run(_execute(db_url, cleanup, {}))
