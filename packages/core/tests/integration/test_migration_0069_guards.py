# pyright: reportPrivateUsage=false
"""``0069_meme_absorb_semdump_arm`` — the upgrade's refusals, in a database of their
own (split from ``test_migration_0069.py`` for the 350-line budget).

What is proved: the upgrade refuses, by name and with nothing seeded, an original
that is retired, off the ``15s`` clock or already without the exit (``false``,
``null`` or the string ``"false"``), and a stranger under the frozen name; an
original that names the switch ``true`` is still paired; and a ``--set-param``
racing the deploy cannot slip between the guards and the copy — the original row
is locked first, so the upgrade waits for the edit and then judges the edited
document (Astra, ``H-031b-diff`` must-fix 2).
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from .conftest import alembic_config, async_engine, create_database, migration_ddl
from .test_migration_0069 import (
    _A_REFUSAL,
    ORIGINAL,
    PREVIOUS,
    REVISION,
    TWIN,
    _count_of,
    _revision_of,
    _scalar,
    _write,
)

pytestmark = pytest.mark.integration

_TO_1M = 'UPDATE meme_rule_sets SET params = params || \'{"clock": "1m"}\'::jsonb WHERE id = :a'
_BLOCKED_BY = (
    "SELECT count(*) FROM pg_stat_activity WHERE CAST(:pid AS int) = ANY(pg_blocking_pids(pid))"
)


def _params_of(url: str, rule_set: str) -> dict[str, Any]:
    return asyncio.run(_scalar(url, "SELECT params FROM meme_rule_sets WHERE id = :r", r=rule_set))


@pytest.fixture(scope="module")
def upgraded(container_url: str) -> Iterator[str]:
    """This revision by name, not ``head``, on a database of this file's own."""
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0069_guards"))
    command.upgrade(alembic_config(db_url), REVISION)
    yield db_url


def _refused_upgrade(upgraded: str, damage: str, restore: str, match: str) -> None:
    """Downgrade, damage ``absorb_v0/2``, see the upgrade refuse by name with
    nothing seeded, then repair and come back to this revision."""
    config = alembic_config(upgraded)
    saved = asyncio.run(
        _scalar(upgraded, "SELECT params::text FROM meme_rule_sets WHERE id = :a", a=ORIGINAL)
    )
    target: dict[str, object] = {"a": ORIGINAL, "p": saved}
    try:
        command.downgrade(config, PREVIOUS)
        asyncio.run(_write(upgraded, [(damage, target)]))
        with pytest.raises(DBAPIError, match=match):
            command.upgrade(config, REVISION)
        assert _revision_of(upgraded) == PREVIOUS and _count_of(upgraded, TWIN) == 0
    finally:
        asyncio.run(_write(upgraded, [(restore, target)]))
        command.upgrade(config, REVISION)
    assert _revision_of(upgraded) == REVISION and _count_of(upgraded, TWIN) == 1


_RESTORE = (
    "UPDATE meme_rule_sets SET status = 'active', retired_at = NULL, "
    "params = CAST(:p AS jsonb) WHERE id = :a"
)


def test_the_upgrade_refuses_without_an_active_original(upgraded: str) -> None:
    _refused_upgrade(
        upgraded,
        "UPDATE meme_rule_sets SET status = 'retired', retired_at = now() "
        "WHERE id = :a AND CAST(:p AS text) IS NOT NULL",
        _RESTORE,
        "absorb_v0/2 is missing or not active",
    )


@pytest.mark.parametrize(
    "clock_sql",
    [
        'params || \'{"clock": "1m"}\'::jsonb',
        "params - 'clock'",
        "params || '{\"clock\": null}'::jsonb",
    ],
)
def test_the_upgrade_refuses_when_the_original_is_not_on_the_15s_clock(
    upgraded: str, clock_sql: str
) -> None:
    _refused_upgrade(
        upgraded,
        f"UPDATE meme_rule_sets SET params = {clock_sql} "  # noqa: S608 - parametrize constants
        "WHERE id = :a AND CAST(:p AS text) IS NOT NULL",
        _RESTORE,
        "absorb_v0/2 is not on the 15s clock",
    )


@pytest.mark.parametrize("switch", ["false", "null", '"false"'])
def test_the_upgrade_refuses_an_original_that_already_ignores_the_dump(
    upgraded: str, switch: str
) -> None:
    """A twin of a set that does not sell on the dump is a copy, not a counterfactual;
    anything but the key absent or ``true`` is refused (``null``/``"false"`` included)."""
    _refused_upgrade(
        upgraded,
        "UPDATE meme_rule_sets SET params = params || "  # noqa: S608 - parametrize constants
        f"'{{\"exit_on_creator_dump\": {switch}}}'::jsonb "
        "WHERE id = :a AND CAST(:p AS text) IS NOT NULL",
        _RESTORE,
        "absorb_v0/2 does not plainly sell on the creator dump",
    )


def test_an_original_that_names_the_switch_on_is_still_paired(upgraded: str) -> None:
    config = alembic_config(upgraded)
    saved = asyncio.run(
        _scalar(upgraded, "SELECT params::text FROM meme_rule_sets WHERE id = :a", a=ORIGINAL)
    )
    target: dict[str, object] = {"a": ORIGINAL, "p": saved}
    on = (
        "UPDATE meme_rule_sets SET params = params || '{\"exit_on_creator_dump\": true}'::jsonb "
        "WHERE id = :a AND CAST(:p AS text) IS NOT NULL"
    )
    try:
        command.downgrade(config, PREVIOUS)
        asyncio.run(_write(upgraded, [(on, target)]))
        command.upgrade(config, REVISION)
        assert _params_of(upgraded, TWIN)["exit_on_creator_dump"] is False
    finally:
        command.downgrade(config, PREVIOUS)
        asyncio.run(_write(upgraded, [(_RESTORE, target)]))
        command.upgrade(config, REVISION)
    twin, original = _params_of(upgraded, TWIN), _params_of(upgraded, ORIGINAL)
    assert "exit_on_creator_dump" not in original, "the original is back as it was"
    assert {k: v for k, v in twin.items() if k != "exit_on_creator_dump"} == original


def test_the_upgrade_refuses_a_stranger_under_the_frozen_name(upgraded: str) -> None:
    config = alembic_config(upgraded)
    stranger = (
        "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status) "
        "VALUES ('01994d00-6c1a-7000-8000-0000000000f9', 'absorb_semdump_v0', '1', "
        "'research_only', '{}'::jsonb, 'stranger', 'EXP-M27', 'active')"
    )
    remove: tuple[str, dict[str, object]] = (
        "DELETE FROM meme_rule_sets WHERE id = '01994d00-6c1a-7000-8000-0000000000f9'",
        {},
    )
    try:
        command.downgrade(config, PREVIOUS)
        asyncio.run(_write(upgraded, [(stranger, {})]))
        with pytest.raises(DBAPIError, match="refusing to pair H-031b against a stranger"):
            command.upgrade(config, REVISION)
        assert _revision_of(upgraded) == PREVIOUS and _count_of(upgraded, TWIN) == 0
    finally:
        asyncio.run(_write(upgraded, [remove]))
        command.upgrade(config, REVISION)
    assert _revision_of(upgraded) == REVISION and _count_of(upgraded, TWIN) == 1


def test_a_concurrent_edit_of_the_original_is_waited_for_and_then_judged(upgraded: str) -> None:
    """Hold the original's row lock, start the upgrade, see it **blocked by this very
    backend** (``pg_blocking_pids``, not a sleep - Astra, db-0069-twin must-fix 2),
    move the clock to ``1m`` and commit: the upgrade then refuses the edited document
    by name. Without the lock nothing is ever blocked and the test fails."""
    config = alembic_config(upgraded)
    saved = asyncio.run(
        _scalar(upgraded, "SELECT params::text FROM meme_rule_sets WHERE id = :a", a=ORIGINAL)
    )
    outcome: dict[str, object] = {}

    def upgrade() -> None:
        try:
            command.upgrade(config, REVISION)
        except DBAPIError as exc:
            outcome["error"] = str(exc)

    async def hold_then_edit() -> threading.Thread:
        engine = async_engine(upgraded)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("SELECT 1 FROM meme_rule_sets WHERE id = :a FOR UPDATE"), {"a": ORIGINAL}
                )
                pid = await connection.scalar(text("SELECT pg_backend_pid()"))
                worker = threading.Thread(target=upgrade)
                worker.start()
                outcome["waited"] = False
                for _ in range(120):  # up to 30 s for alembic to start and reach the lock
                    async with engine.connect() as watcher:
                        if await watcher.scalar(text(_BLOCKED_BY), {"pid": pid}):
                            outcome["waited"] = worker.is_alive()
                            break
                    await asyncio.sleep(0.25)
                await connection.execute(text(_TO_1M), {"a": ORIGINAL})
        finally:
            await engine.dispose()
        return worker

    command.downgrade(config, PREVIOUS)
    try:
        worker = asyncio.run(hold_then_edit())
        worker.join(timeout=120)
        assert not worker.is_alive(), "the upgrade must finish once the edit commits"
        assert outcome.get("waited") is True, "the upgrade must wait on the original's row"
        assert "absorb_v0/2 is not on the 15s clock" in str(outcome.get("error"))
        assert _revision_of(upgraded) == PREVIOUS
        assert _count_of(upgraded, TWIN) == 0
    finally:
        asyncio.run(_write(upgraded, [(_RESTORE, {"a": ORIGINAL, "p": saved})]))
        command.upgrade(config, REVISION)
    assert _revision_of(upgraded) == REVISION
    assert _count_of(upgraded, TWIN) == 1


def test_the_lock_stops_an_edit_of_the_original_but_not_the_workers_inserts(
    upgraded: str,
) -> None:
    """The migration's own ``_LOCK``, held open: an edit of the original (what
    ``--set-param`` and ``--deprecate`` do) times out; a worker's insert of a row
    that references the original (its foreign-key check takes ``FOR KEY SHARE``)
    goes through. ``FOR UPDATE`` would stall that insert for the whole migration."""
    lock = migration_ddl("meme_absorb_semdump_arm")._LOCK

    async def probe() -> None:
        engine = async_engine(upgraded)
        try:
            async with engine.connect() as holder, engine.connect() as other:
                await holder.begin()
                await holder.execute(text(lock))
                await other.begin()
                await other.execute(text("SET LOCAL lock_timeout = '1s'"))
                await other.execute(text(_A_REFUSAL), {"rule_set": ORIGINAL})
                await other.rollback()
                await other.begin()
                await other.execute(text("SET LOCAL lock_timeout = '1s'"))
                with pytest.raises(DBAPIError, match="lock timeout"):
                    await other.execute(text(_TO_1M), {"a": ORIGINAL})
                await other.rollback()
                await holder.rollback()
        finally:
            await engine.dispose()

    asyncio.run(probe())
