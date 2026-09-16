"""``0047_meme_bonding_curve_raw`` against a real Postgres (T4.39/R36): one
nullable ``meme_tokens.bonding_curve_raw`` column, the write-once trigger
extended to cover it, and a downgrade that refuses while any row carries a
raw sighting.

A **new file** on purpose (the brief forbids editing ``test_migrations.py``
for this task): the fixture below upgrades to **this revision by name**
(``"0047_meme_bonding_curve_raw"``), never ``"head"``, the same reasoning
``test_migration_0046.py`` gives for its own revision.

Run alone (``timeout 590``): it shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from .conftest import alembic_config, async_engine, create_database

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

REVISION = "0047_meme_bonding_curve_raw"
PRIOR_REVISION = "0046_meme_rule_set_history"
COLUMN = "bonding_curve_raw"

_MINT = "HTEqdy7kiWFTXrecd1UiMxtU53MP2o1Ybof7wLPBpump"
_CURVE = "Ck72XTyTQYsksoHeHBB48eyY5hmHNcwESXJKEeSCSrHQ"
_SOL_VAULT = "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"


async def _revision(url: str) -> str | None:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def cycle_db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_0047"))


@pytest.fixture(scope="module")
def upgraded(cycle_db_url: str) -> Iterator[str]:
    """``alembic upgrade 0047_meme_bonding_curve_raw`` on a clean database."""
    command.upgrade(alembic_config(cycle_db_url), REVISION)
    yield cycle_db_url


@pytest_asyncio.fixture
async def engine(upgraded: str) -> AsyncIterator[AsyncEngine]:
    created = async_engine(upgraded)
    try:
        yield created
    finally:
        await created.dispose()


async def _insert_token(engine: AsyncEngine, mint: str, bonding_curve: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_tokens (mint, bonding_curve, first_seen_source, "
                "  first_seen_at, last_seen_at) "
                "VALUES (:mint, :bonding_curve, 'pumpportal_ws', now(), now())"
            ),
            {"mint": mint, "bonding_curve": bonding_curve},
        )


def test_upgrading_to_0047_does_not_raise(upgraded: str) -> None:
    assert asyncio.run(_revision(upgraded)) == REVISION


async def test_the_column_exists_nullable_and_starts_empty(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT is_nullable, data_type FROM information_schema.columns "
                    "WHERE table_name = 'meme_tokens' AND column_name = :c"
                ),
                {"c": COLUMN},
            )
        ).one()
    assert row.is_nullable == "YES"
    assert row.data_type == "text"


async def test_the_write_once_trigger_now_covers_bonding_curve_raw(engine: AsyncEngine) -> None:
    await _insert_token(engine, _MINT, _CURVE)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                f"UPDATE meme_tokens SET {COLUMN} = :raw WHERE mint = :mint"  # noqa: S608
            ),
            {"raw": _SOL_VAULT, "mint": _MINT},
        )
    with pytest.raises(DBAPIError, match="is written once"):
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    f"UPDATE meme_tokens SET {COLUMN} = :raw WHERE mint = :mint"  # noqa: S608
                ),
                {"raw": "something-else", "mint": _MINT},
            )
    async with engine.connect() as connection:
        stored = await connection.scalar(
            text(f"SELECT {COLUMN} FROM meme_tokens WHERE mint = :mint"),  # noqa: S608
            {"mint": _MINT},
        )
    assert stored == _SOL_VAULT, "the refused UPDATE must not have changed the row"


async def test_bonding_curve_itself_is_still_write_once(engine: AsyncEngine) -> None:
    """0047 replaces the trigger function wholesale — pin that the columns
    ``0041`` already guarded (``bonding_curve`` among them) are still guarded,
    not silently dropped by the replacement."""
    mint = f"{_MINT[:-4]}z9pump"
    await _insert_token(engine, mint, _CURVE)
    with pytest.raises(DBAPIError, match="is written once"):
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE meme_tokens SET bonding_curve = :raw WHERE mint = :mint"),
                {"raw": _SOL_VAULT, "mint": mint},
            )


def test_downgrade_refuses_while_a_row_carries_a_raw_value(upgraded: str) -> None:
    config = alembic_config(upgraded)
    with pytest.raises(DBAPIError, match="bonding_curve_raw value"):
        command.downgrade(config, PRIOR_REVISION)
    assert asyncio.run(_revision(upgraded)) == REVISION, (
        "a refused downgrade must not have moved the schema"
    )


async def _clear_bonding_curve_raw(url: str) -> None:
    """The write-once trigger refuses ``NULL`` too — a raw sighting cleared is
    still ``NEW IS DISTINCT FROM OLD`` — so an operator preparing a downgrade
    must disable it first, the same discipline the trigger's own installer
    (``_install``/``create_meme_token_guards_0047``) and
    ``infra/scripts/meme_repair_bonding_curve.py`` use for the same table."""
    trigger = "meme_tokens_identity_is_written_once"
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"ALTER TABLE meme_tokens DISABLE TRIGGER {trigger}"))
            await connection.execute(text(f"UPDATE meme_tokens SET {COLUMN} = NULL"))  # noqa: S608
            await connection.execute(text(f"ALTER TABLE meme_tokens ENABLE TRIGGER {trigger}"))
    finally:
        await engine.dispose()


def test_downgrade_succeeds_once_every_row_is_cleared_and_upgrade_comes_back_clean(
    cycle_db_url: str,
) -> None:
    """Sync (module docstring): ``env.py`` calls ``asyncio.run``, which cannot
    run inside pytest-asyncio's already-running loop."""
    asyncio.run(_clear_bonding_curve_raw(cycle_db_url))
    config = alembic_config(cycle_db_url)
    command.downgrade(config, PRIOR_REVISION)
    assert asyncio.run(_revision(cycle_db_url)) == PRIOR_REVISION
    command.upgrade(config, REVISION)
    assert asyncio.run(_revision(cycle_db_url)) == REVISION
