"""The partition pruner against a real Postgres: it never jams the ingestion.

``docs/design/retencao-e-disco-2026-09-27.md`` §6 (passo 2c): the pruner ran
every ``DETACH``/``DROP`` in one transaction with no ``lock_timeout``. A
``DETACH`` asks for ``ACCESS EXCLUSIVE``; arriving during the 80-minute nightly
``pg_dump`` (``ACCESS SHARE`` on every table) it queued, and every ``INSERT``
into that parent queued behind it until the dump ended. Four properties:

1. a partition whose lock is not granted within the timeout is skipped **by
   name** and the others still go — each in a transaction of its own, so one
   dropped before the stuck one stays dropped;
2. any other error on one partition is recorded and the run moves on;
3. while a ``pg_dump`` is connected to the database nothing is touched;
4. the CLI says so with exit 75 (``EX_TEMPFAIL``, as ``create_partitions.py``)
   and leaves a ``system_events`` row naming what it skipped.

Run:
    uv run pytest infra/scripts/tests/test_prune_partitions_integration.py -q
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_core.db.models import create_partition_sql

if TYPE_CHECKING:
    from collections.abc import Generator

    from testcontainers.community.postgres import PostgresContainer

pytestmark = pytest.mark.integration

SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load_prune() -> ModuleType:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        "hunter_infra_prune_partitions_it", SCRIPTS_DIR / "prune_partitions.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def _execute(url: str, *statements: str, **params: Any) -> list[Any]:
    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.begin() as connection:
            results = [await connection.execute(text(sql), params) for sql in statements]
            return [result.all() if result.returns_rows else [] for result in results]
    finally:
        await engine.dispose()


def _create(url: str, *months: tuple[int, int]) -> list[str]:
    """Stale ``candles_1m`` months (2025, far past the 90-day window)."""
    asyncio.run(_execute(url, *(create_partition_sql("candles_1m", year, m) for year, m in months)))
    return [f"candles_1m_{year:04d}_{m:02d}" for year, m in months]


def _attached(url: str) -> set[str]:
    (rows,) = asyncio.run(
        _execute(
            url,
            "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
            "WHERE c.relname LIKE 'candles_1m_2025_%'",
        )
    )
    return {row[0] for row in rows}


def _existing(url: str, names: list[str]) -> set[str]:
    (rows,) = asyncio.run(
        _execute(url, "SELECT relname FROM pg_class WHERE relname = ANY(:names)", names=names)
    )
    return {row[0] for row in rows}


def _cleanup(url: str, names: list[str]) -> None:
    for name in _existing(url, names):
        asyncio.run(_execute(url, f"DROP TABLE IF EXISTS {name}"))


@contextmanager
def _held_connection(
    url: str,
    *,
    application_name: str | None = None,
    lock: str | None = None,
    mode: str = "ACCESS SHARE",
) -> Generator[None]:
    """Another session, on its own thread, alive for the ``with`` block.

    ``application_name='pg_dump'`` is how a real ``pg_dump`` shows up in
    ``pg_stat_activity`` (its libpq ``fallback_application_name``, proved with
    the real binary below); ``lock`` holds ``mode`` on a table in an open
    transaction — ``ACCESS SHARE`` is what the dump holds on every table.
    """
    ready, release = threading.Event(), threading.Event()
    failure: list[BaseException] = []

    async def _hold() -> None:
        settings = {"application_name": application_name} if application_name else {}
        engine = create_async_engine(
            url, connect_args={"statement_cache_size": 0, "server_settings": settings}
        )
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))  # opens the transaction
                if lock is not None:
                    await connection.execute(text(f"LOCK TABLE {lock} IN {mode} MODE"))
                ready.set()
                await asyncio.to_thread(release.wait)
                await connection.rollback()
        finally:
            await engine.dispose()

    def _run() -> None:
        try:
            asyncio.run(_hold())
        except BaseException as exc:  # surfaced to the test below
            failure.append(exc)
            ready.set()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    assert ready.wait(30), "the holding session never came up"
    if failure:
        raise failure[0]
    try:
        yield
    finally:
        release.set()
        thread.join(30)


def test_a_locked_partition_is_skipped_by_name_and_the_others_still_commit(
    migrated_db_url: str,
) -> None:
    os.environ["DATABASE_URL_MIGRATIONS"] = migrated_db_url
    prune = _load_prune()
    first, stuck, last = _create(migrated_db_url, (2025, 1), (2025, 2), (2025, 3))
    statements = prune.planned_statements([("candles_1m", n) for n in (first, stuck, last)])
    report = prune.PruneReport()
    try:
        with _held_connection(migrated_db_url, lock=stuck):
            dropped = asyncio.run(prune.prune(statements, report))
            # Checked while the lock is still held: `first` came before the
            # stuck one, so under the old single transaction it would have
            # been rolled back with it.
            assert _existing(migrated_db_url, [first, stuck, last]) == {stuck}
        assert dropped == [first, last]
        assert report.dropped == [first, last]
        assert list(report.skipped) == [stuck]
        assert "lock_timeout" in report.skipped[stuck]
        assert report.failed == {}
        assert _attached(migrated_db_url) >= {stuck}, "the skipped month is left attached"
    finally:
        _cleanup(migrated_db_url, [first, stuck, last])


def test_a_failing_partition_is_recorded_and_the_run_moves_on(migrated_db_url: str) -> None:
    os.environ["DATABASE_URL_MIGRATIONS"] = migrated_db_url
    prune = _load_prune()
    broken, fine = _create(migrated_db_url, (2025, 4), (2025, 5))
    statements = [
        # wrong parent: Postgres refuses the DETACH ("is not a partition of")
        (broken, f"ALTER TABLE candles_1h DETACH PARTITION {broken}"),
        (broken, f"DROP TABLE IF EXISTS {broken}"),
        *prune.planned_statements([("candles_1m", fine)]),
    ]
    report = prune.PruneReport()
    try:
        dropped = asyncio.run(prune.prune(statements, report))
        assert dropped == [fine]
        assert list(report.failed) == [broken]
        assert report.skipped == {}
        assert _existing(migrated_db_url, [broken, fine]) == {broken}
    finally:
        _cleanup(migrated_db_url, [broken, fine])


def test_nothing_is_touched_while_a_pg_dump_is_connected(migrated_db_url: str) -> None:
    os.environ["DATABASE_URL_MIGRATIONS"] = migrated_db_url
    prune = _load_prune()
    names = _create(migrated_db_url, (2025, 6), (2025, 7))
    statements = prune.planned_statements([("candles_1m", n) for n in names])
    report = prune.PruneReport()
    try:
        with _held_connection(migrated_db_url, application_name="pg_dump"):
            dropped = asyncio.run(prune.prune(statements, report))
        assert dropped == []
        assert report.dump_active is True
        assert sorted(report.skipped) == names
        assert all("pg_dump" in reason for reason in report.skipped.values())
        assert _attached(migrated_db_url) >= set(names)

        # the dump is gone: the same plan now goes through
        assert asyncio.run(prune.prune(statements)) == names
    finally:
        _cleanup(migrated_db_url, names)


def test_the_cli_refuses_with_75_and_leaves_a_system_event(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    os.environ["DATABASE_URL_MIGRATIONS"] = migrated_db_url
    prune = _load_prune()
    names = _create(migrated_db_url, (2025, 8))
    events = "SELECT count(*) FROM system_events WHERE component = 'prune_partitions'"
    ((before,),) = asyncio.run(_execute(migrated_db_url, events))[0]
    try:
        monkeypatch.setattr(sys, "argv", ["prune_partitions.py", "--dry-run"])
        assert prune.main() == 0
        assert asyncio.run(_execute(migrated_db_url, events))[0] == [(before,)], "dry-run wrote"

        monkeypatch.setattr(sys, "argv", ["prune_partitions.py"])
        with _held_connection(migrated_db_url, application_name="pg_dump"):
            code = prune.main()
        assert code == 75
        assert _attached(migrated_db_url) >= set(names)
        assert asyncio.run(_execute(migrated_db_url, events))[0] == [(before + 1,)]
        (rows,) = asyncio.run(
            _execute(
                migrated_db_url,
                "SELECT level::text, event, data FROM system_events "
                "WHERE component = 'prune_partitions' ORDER BY created_at DESC, id DESC LIMIT 1",
            )
        )
        level, event, data = rows[0]
        data = cast("dict[str, Any]", data if isinstance(data, dict) else json.loads(data))
        assert (level, event) == ("warning", "partitions_pruned")
        assert data["dump_active"] is True
        assert data["dropped"] == []
        assert names[0] in data["skipped"]
    finally:
        _cleanup(migrated_db_url, names)


def _dump_sessions(url: str) -> int:
    (rows,) = asyncio.run(
        _execute(url, "SELECT count(*) FROM pg_stat_activity WHERE application_name = 'pg_dump'")
    )
    return int(rows[0][0])


def test_the_real_pg_dump_binary_is_what_the_check_sees(
    migrated_db_url: str, postgres_container: PostgresContainer
) -> None:
    """The check rests on libpq naming every ``pg_dump`` session ``pg_dump``.

    The backup runs ``pg_dump -U hunter -d hunter`` inside the postgres
    container with no ``PGAPPNAME`` (``infra/vps/backup_postgres.sh``). Here the
    same binary, in the same kind of container, is kept connected by an
    ``ACCESS EXCLUSIVE`` lock it waits on — the name is read, not assumed.
    """
    os.environ["DATABASE_URL_MIGRATIONS"] = migrated_db_url
    prune = _load_prune()
    names = _create(migrated_db_url, (2025, 9))
    statements = prune.planned_statements([("candles_1m", n) for n in names])
    report = prune.PruneReport()
    database = migrated_db_url.rsplit("/", 1)[1]
    try:
        with _held_connection(migrated_db_url, lock="exchanges", mode="ACCESS EXCLUSIVE"):
            postgres_container.get_wrapped_container().exec_run(
                ["pg_dump", "-U", postgres_container.username, "-d", database, "-f", "/dev/null"],
                environment={"PGPASSWORD": postgres_container.password},
                detach=True,
            )
            for _ in range(100):
                if _dump_sessions(migrated_db_url):
                    break
                time.sleep(0.1)
            assert _dump_sessions(migrated_db_url) == 1, "pg_dump never showed up as 'pg_dump'"
            assert asyncio.run(prune.prune(statements, report)) == []
        assert report.dump_active is True
        assert _attached(migrated_db_url) >= set(names)
        for _ in range(300):  # the dump finishes once the lock is gone
            if not _dump_sessions(migrated_db_url):
                break
            time.sleep(0.1)
        assert _dump_sessions(migrated_db_url) == 0
    finally:
        _cleanup(migrated_db_url, names)
