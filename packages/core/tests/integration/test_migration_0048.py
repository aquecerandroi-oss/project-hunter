"""``0048_meme_creator_initial_buy`` (T4.45) — its own file and its own database.

A new file because ``test_migrations.py`` was being committed by another task
while this revision was written; its ``HEAD_REVISION`` still says ``0047`` and
has to be bumped to ``0048`` by whoever lands this (the assertions that notice
are ``test_upgrade_reaches_head``-style equalities and
``ids[-1] == HEAD_REVISION``). Nothing here depends on that constant.

What is proved: the columns exist with the neighbours' type and stay nullable;
the write-once trigger covers them (a *current* reading may never rewrite the
creation instant's allocation — the whole reason the column exists); a negative
allocation is refused; the downgrade refuses while any row carries the value and
restores ``0047``'s trigger shape when none does.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database, migration_ddl

pytestmark = pytest.mark.integration

REVISION = "0048_meme_creator_initial_buy"
PREVIOUS = "0047_meme_bonding_curve_raw"
COLUMNS = ("creator_initial_tokens", "creator_initial_sol")


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0048"))


@pytest.fixture(scope="module")
def upgraded(db_url: str) -> Iterator[str]:
    """``alembic upgrade head`` on a clean database of this revision's own."""
    command.upgrade(alembic_config(db_url), "head")
    yield db_url


@pytest_asyncio.fixture
async def engine(upgraded: str) -> AsyncIterator[AsyncEngine]:
    created = async_engine(upgraded)
    try:
        yield created
    finally:
        await created.dispose()


@pytest_asyncio.fixture
async def clean(engine: AsyncEngine) -> AsyncIterator[None]:
    """Every test owns the table: a leftover row would decide the downgrade
    guard's answer for the next one.

    ``app.meme_retention`` is the schema's own rule — discovery history is not
    deleted by accident, only by something that says it is retention. A test
    cleaning up after itself is exactly that, and declaring it here keeps the
    guard honest instead of dropping it."""
    await _purge(engine)
    yield
    await _purge(engine)


async def _purge(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("SET LOCAL app.meme_retention = 'on'"))
        await connection.execute(text("DELETE FROM meme_tokens WHERE mint LIKE 't4045%'"))


async def _insert(engine: AsyncEngine, mint: str, **values: object) -> None:
    columns = ("mint", "first_seen_source", "first_seen_at", "last_seen_at", *values)
    extra = "".join(f", :{name}" for name in values)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                f"INSERT INTO meme_tokens ({', '.join(columns)}) "  # noqa: S608
                f"VALUES (:mint, 'pumpportal_ws', now(), now(){extra})"
            ),
            {"mint": mint, **values},
        )


async def _revision_of(url: str) -> str | None:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await engine.dispose()


async def _columns_present(url: str) -> set[str]:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            return set(
                (
                    await connection.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'meme_tokens' AND column_name = ANY(:columns)"
                        ),
                        {"columns": list(COLUMNS)},
                    )
                ).scalars()
            )
    finally:
        await engine.dispose()


async def _seed_and_touch(url: str, mint: str, **values: object) -> None:
    """Insert a token and move a *mutable* column on it — the UPDATE any radar
    cycle does, and the one a trigger left pointing at a dropped column would
    break."""
    engine = async_engine(url)
    try:
        await _insert(engine, mint, **values)
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE meme_tokens SET last_seen_at = now() WHERE mint = :mint"),
                {"mint": mint},
            )
    finally:
        await engine.dispose()


async def _purge_url(url: str) -> None:
    engine = async_engine(url)
    try:
        await _purge(engine)
    finally:
        await engine.dispose()


def test_the_revision_lands_on_0047() -> None:
    """Pure: no database, no container — the chain this task was told to extend.

    Read as text: importing the module would execute ``from ddl...`` imports that
    only resolve with ``infra/migrations`` on the path, and this assertion is
    about two literals, not about Alembic being importable."""
    source = (REPO_ROOT / "infra" / "migrations" / "versions" / f"{REVISION}.py").read_text(
        encoding="utf-8"
    )
    assert f'revision: str = "{REVISION}"' in source
    assert f'down_revision: str | None = "{PREVIOUS}"' in source


def test_the_ddl_module_freezes_0047s_write_once_list_before_adding_its_own() -> None:
    """The downgrade restores a list; if that list drifts from what ``0047``
    actually installed, reversing this revision would quietly stop protecting a
    column. Copied constants are only safe while they are compared."""
    ddl_0047 = migration_ddl("meme_bonding_curve_raw")
    ddl_0048 = migration_ddl("meme_creator_initial_buy")
    assert ddl_0048.WRITE_ONCE_COLUMNS_FULL_0047 == ddl_0047.WRITE_ONCE_COLUMNS_FULL_0047
    assert ddl_0048.WRITE_ONCE_COLUMNS_FULL_0048 == (
        *ddl_0047.WRITE_ONCE_COLUMNS_FULL_0047,
        *COLUMNS,
    )


@pytest.mark.asyncio
async def test_the_two_columns_exist_with_the_denominators_own_type(engine: AsyncEngine) -> None:
    """Same ``numeric(28, 10)`` as ``initial_real_token_reserves``: the creator's
    slice and the curve's denominator are compared, so they share a type."""
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT column_name, data_type, numeric_precision, numeric_scale, "
                    "  is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'meme_tokens' AND column_name = ANY(:columns)"
                ),
                {"columns": list(COLUMNS)},
            )
        ).mappings()
        found = {row["column_name"]: row for row in rows}
    assert set(found) == set(COLUMNS)
    for column in COLUMNS:
        assert found[column]["data_type"] == "numeric"
        assert (found[column]["numeric_precision"], found[column]["numeric_scale"]) == (28, 10)
        assert found[column]["is_nullable"] == "YES", "an unobserved allocation is NULL"


@pytest.mark.asyncio
async def test_the_orm_model_and_the_database_agree(engine: AsyncEngine) -> None:
    from hunter_core.db.models.meme import MemeToken

    mapped = {column.name for column in MemeToken.__table__.columns}
    assert set(COLUMNS) <= mapped
    async with engine.connect() as connection:
        in_db = set(
            (
                await connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'meme_tokens'"
                    )
                )
            ).scalars()
        )
    assert mapped <= in_db


@pytest.mark.asyncio
async def test_a_zero_allocation_is_storable_because_it_is_a_measurement(
    engine: AsyncEngine, clean: None
) -> None:
    """``initialBuy = 0`` happens (a dev who bought nothing at creation) and is
    **observed**. The admission's ``> 0`` rule is what refuses to derive a flow
    from it; the column stores what was seen."""
    await _insert(engine, "t4045-zero", creator_initial_tokens=0, creator_initial_sol=0)
    async with engine.connect() as connection:
        value = await connection.scalar(
            text("SELECT creator_initial_tokens FROM meme_tokens WHERE mint = 't4045-zero'")
        )
    assert value == 0


@pytest.mark.asyncio
async def test_a_negative_allocation_is_refused(engine: AsyncEngine, clean: None) -> None:
    with pytest.raises(DBAPIError, match="a_dev_buy_is_not_negative"):
        await _insert(engine, "t4045-neg", creator_initial_tokens=-1)


@pytest.mark.asyncio
async def test_an_unobserved_allocation_can_still_be_filled_once(
    engine: AsyncEngine, clean: None
) -> None:
    """A mint discovered by a migration frame has no ``create`` frame; when one
    arrives later the ``NULL`` may be filled, exactly like every identity column."""
    await _insert(engine, "t4045-fill")
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_tokens SET creator_initial_tokens = 30877830.227113, "
                "  creator_initial_sol = 0.888892813 WHERE mint = 't4045-fill'"
            )
        )
        value = await connection.scalar(
            text("SELECT creator_initial_tokens FROM meme_tokens WHERE mint = 't4045-fill'")
        )
    assert value is not None and float(value) == pytest.approx(30877830.227113)


@pytest.mark.asyncio
@pytest.mark.parametrize("column", COLUMNS)
async def test_the_creators_allocation_is_written_once(
    engine: AsyncEngine, clean: None, column: str
) -> None:
    """The failure this guard closes: a later *current* reading (the indexer's
    ``devHoldingsPercent``, a repair script, a re-ingest of a mint) overwrites
    the creation instant's allocation with what the creator holds **now**. The
    executor then compares his balance against his own current balance, finds
    them equal, and passes check 10 for a creator who dumped everything — the
    exact bug T4.28g §2.3 refused to write."""
    await _insert(engine, "t4045-once", **{column: 1000})
    with pytest.raises(DBAPIError, match="written once"):
        async with engine.begin() as connection:
            await connection.execute(
                text(f"UPDATE meme_tokens SET {column} = 1 WHERE mint = 't4045-once'")  # noqa: S608
            )


def test_the_downgrade_refuses_while_an_allocation_is_recorded(upgraded: str) -> None:
    """§17.7 — the ``create`` frame has no replay, so dropping the column is
    destructive. The reversal says so and stops; the database stays on ``0048``.

    Sync, like every Alembic-driving test in this suite: ``env.py`` calls
    ``asyncio.run``, which raises inside a running loop."""
    # T4.48: staged at ``0048`` first — ``0049_meme_gate_buyers25_arm`` sits on
    # top, so ``"-1"`` from the head reverses *that* seed, not this revision.
    config = alembic_config(upgraded)
    command.downgrade(config, REVISION)
    asyncio.run(_seed_and_touch(upgraded, "t4045-guard", creator_initial_tokens=1000))
    try:
        with pytest.raises(Exception, match="not re-observable"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision_of(upgraded)) == REVISION
        assert asyncio.run(_columns_present(upgraded)) == set(COLUMNS)
    finally:
        asyncio.run(_purge_url(upgraded))
        command.upgrade(config, "head")


def test_the_downgrade_reverses_cleanly_when_nothing_was_observed(upgraded: str) -> None:
    """And puts ``0047``'s trigger back **before** the columns it would otherwise
    still name are dropped — a function referencing a dropped column raises on
    the next UPDATE of *any* token, which would take the radar down while the
    operator thinks he only reversed one revision."""
    asyncio.run(_purge_url(upgraded))
    config = alembic_config(upgraded)
    # T4.48: the same staging as the guard test above — ``"-1"`` stopped meaning
    # ``0048`` the day ``0049`` landed on top.
    command.downgrade(config, REVISION)
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_revision_of(upgraded)) == PREVIOUS
        assert asyncio.run(_columns_present(upgraded)) == set()
        asyncio.run(_seed_and_touch(upgraded, "t4045-after", creator="someone"))
    finally:
        asyncio.run(_purge_url(upgraded))
        command.upgrade(config, "head")
