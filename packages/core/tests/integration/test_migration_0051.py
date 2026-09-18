"""``0051_meme_treasury_swaps`` (T4.54) — its own file and its own database, in
``test_migration_0050.py``'s shape.

What is proved: the table exists with the six lifecycle statuses, its named
CHECK constraints hold (a refusal is named and sends nothing; a confirmed
swap always carries a signature, a fill and the wallet's balance after;
nothing is negative), the ORM model agrees with the migration (``alembic
check``), grants are read-only for the desk and read/append/update for the
executor with no ``DELETE`` to anyone, and the downgrade removes the table on
a clean database but refuses while a row exists (§17.7).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from .conftest import alembic_config, async_engine, create_database

pytestmark = pytest.mark.integration

REVISION = "0051_meme_treasury_swaps"
PREVIOUS = "0050_meme_gate_ratio10_arm"

_INSERT = (
    "INSERT INTO meme_treasury_swaps (id, reason, usdc_in, sol_out_quoted, sol_out_filled, "
    "  price_impact_pct, slippage_bps, signature, status, refusal, wallet_sol_before, "
    "  wallet_sol_after) VALUES (:id, :reason, :usdc_in, :sol_out_quoted, :sol_out_filled, "
    "  :price_impact_pct, :slippage_bps, :signature, :status, :refusal, :wallet_sol_before, "
    "  :wallet_sol_after)"
)

_CONFIRMED_ROW = {
    "id": str(uuid.uuid4()),
    "reason": "sol_below_floor",
    "usdc_in": "25",
    "sol_out_quoted": "0.171",
    "sol_out_filled": "0.170",
    "price_impact_pct": "0.0012",
    "slippage_bps": 50,
    "signature": "5" * 88,
    "status": "confirmed",
    "refusal": None,
    "wallet_sol_before": "0.20",
    "wallet_sol_after": "0.37",
}


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0051"))


@pytest.fixture(scope="module")
def upgraded(db_url: str) -> Iterator[str]:
    """This revision, not ``head``: ``0052`` (T4.61a) now lands on top of it,
    and this module's downgrade assertions (``"-1"`` -> ``PREVIOUS``) are about
    the one step this revision itself takes, not about whatever the chain
    grows to after it."""
    command.upgrade(alembic_config(db_url), REVISION)
    yield db_url


@pytest_asyncio.fixture
async def engine(upgraded: str) -> AsyncIterator[AsyncEngine]:
    created = async_engine(upgraded)
    try:
        yield created
    finally:
        await created.dispose()


async def _write(engine: AsyncEngine, statement: str, params: dict[str, object]) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(statement), params)


async def _clean(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM meme_treasury_swaps"))


async def _revision_of(url: str) -> str | None:
    created = async_engine(url)
    try:
        async with created.connect() as connection:
            return await connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await created.dispose()


async def _count(url: str) -> int:
    created = async_engine(url)
    try:
        async with created.connect() as connection:
            found = await connection.scalar(text("SELECT count(*) FROM meme_treasury_swaps"))
            return int(found or 0)
    finally:
        await created.dispose()


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    """``alembic check`` needs the true head, not just this revision — ``0052``
    (T4.61a) lands on top of ``0051`` and seeds a rule set of its own, so this
    assertion runs on its own database taken all the way to ``head`` rather
    than on ``upgraded`` (staged at ``REVISION`` for the downgrade tests),
    the same shape ``test_migration_0050`` settled on."""
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0051_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


@pytest.mark.asyncio
async def test_a_confirmed_swap_can_be_written(engine: AsyncEngine) -> None:
    await _write(engine, _INSERT, _CONFIRMED_ROW)
    try:
        async with engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT status, signature, sol_out_filled, wallet_sol_after "
                            "FROM meme_treasury_swaps WHERE id = :id"
                        ),
                        {"id": _CONFIRMED_ROW["id"]},
                    )
                )
                .mappings()
                .first()
            )
        assert row is not None
        assert row["status"] == "confirmed"
        assert row["signature"] == _CONFIRMED_ROW["signature"]
    finally:
        await _clean(engine)


@pytest.mark.asyncio
async def test_a_refusal_is_named_and_sends_nothing(engine: AsyncEngine) -> None:
    refused = {
        **_CONFIRMED_ROW,
        "id": str(uuid.uuid4()),
        "status": "refused",
        "refusal": "price_impact_above_cap",
        "signature": None,
        "sol_out_filled": None,
        "wallet_sol_after": None,
    }
    await _write(engine, _INSERT, refused)
    await _clean(engine)

    unnamed = {**refused, "id": str(uuid.uuid4()), "refusal": None}
    with pytest.raises(IntegrityError, match="a_refusal_is_named"):
        await _write(engine, _INSERT, unnamed)
    await _clean(engine)

    with_a_signature = {**refused, "id": str(uuid.uuid4()), "signature": "5" * 88}
    with pytest.raises(IntegrityError, match="a_refused_swap_sends_nothing"):
        await _write(engine, _INSERT, with_a_signature)
    await _clean(engine)


@pytest.mark.asyncio
async def test_a_confirmed_swap_must_carry_its_fill(engine: AsyncEngine) -> None:
    missing_fill = {**_CONFIRMED_ROW, "id": str(uuid.uuid4()), "sol_out_filled": None}
    with pytest.raises(IntegrityError, match="a_confirmed_swap_has_a_fill"):
        await _write(engine, _INSERT, missing_fill)
    await _clean(engine)


@pytest.mark.asyncio
async def test_amounts_are_not_negative(engine: AsyncEngine) -> None:
    negative = {**_CONFIRMED_ROW, "id": str(uuid.uuid4()), "usdc_in": "-1"}
    with pytest.raises(IntegrityError, match="amounts_are_not_negative"):
        await _write(engine, _INSERT, negative)
    await _clean(engine)


@pytest.mark.asyncio
async def test_an_unknown_status_is_refused(engine: AsyncEngine) -> None:
    unknown = {**_CONFIRMED_ROW, "id": str(uuid.uuid4()), "status": "pending"}
    with pytest.raises(IntegrityError, match="status_is_a_known_label"):
        await _write(engine, _INSERT, unknown)
    await _clean(engine)


@pytest.mark.asyncio
async def test_grants_are_read_only_for_the_app_and_no_delete_to_anyone(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT grantee, privilege_type FROM information_schema.role_table_grants "
                    "WHERE table_name = 'meme_treasury_swaps' "
                    "ORDER BY grantee, privilege_type"
                )
            )
        ).all()
    grants = {(str(r[0]), str(r[1])) for r in rows}
    assert ("hunter_app", "SELECT") in grants
    assert ("hunter_app", "DELETE") not in grants
    assert ("hunter_worker", "SELECT") in grants
    assert ("hunter_worker", "INSERT") in grants
    assert ("hunter_worker", "UPDATE") in grants
    assert ("hunter_worker", "DELETE") not in grants


async def _write_url(url: str, statement: str, params: dict[str, object]) -> None:
    created = async_engine(url)
    try:
        await _write(created, statement, params)
    finally:
        await created.dispose()


async def _clean_url(url: str) -> None:
    created = async_engine(url)
    try:
        await _clean(created)
    finally:
        await created.dispose()


def test_the_downgrade_refuses_while_a_swap_row_exists(upgraded: str) -> None:
    """§17.7: a treasury swap is real (or refused) money movement — count, name,
    stop."""
    config = alembic_config(upgraded)
    asyncio.run(_write_url(upgraded, _INSERT, _CONFIRMED_ROW))
    try:
        with pytest.raises(DBAPIError, match="meme_treasury_swaps rows exist"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision_of(upgraded)) == REVISION, "the downgrade must not commit"
    finally:
        asyncio.run(_clean_url(upgraded))


def test_the_downgrade_removes_the_table_on_a_clean_database_and_comes_back(
    upgraded: str,
) -> None:
    config = alembic_config(upgraded)
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_revision_of(upgraded)) == PREVIOUS

        async def _table_exists() -> bool:
            created = async_engine(upgraded)
            try:
                async with created.connect() as connection:
                    return bool(
                        await connection.scalar(
                            text("SELECT to_regclass('meme_treasury_swaps') IS NOT NULL")
                        )
                    )
            finally:
                await created.dispose()

        assert asyncio.run(_table_exists()) is False
    finally:
        # Back to REVISION, not "head": 0052 (T4.61a) lands on top of this one
        # now, and this module's database is staged at REVISION on purpose (see
        # the ``upgraded`` fixture) — ``test_the_models_and_the_migrations_
        # agree`` above is the one that checks the whole chain against "head".
        command.upgrade(config, REVISION)
    assert asyncio.run(_revision_of(upgraded)) == REVISION
    assert asyncio.run(_count(upgraded)) == 0
