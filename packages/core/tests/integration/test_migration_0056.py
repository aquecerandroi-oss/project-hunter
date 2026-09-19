"""``0056_meme_spot_swaps`` (T4.73) — the two nullable mint-pair columns on
``meme_treasury_swaps``, ``test_migration_0051.py``'s shape.

What is proved: both columns start ``NULL`` on a row written before this
revision (the USDC->SOL treasury path never sets them), a spot-swap row can
carry both together, the paired CHECK refuses one set without the other, the
ORM model agrees with the migration (``alembic check``), and the downgrade
drops the columns on a clean database but refuses while any row names a pair
(§17.7).
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

REVISION = "0056_meme_spot_swaps"
PREVIOUS = "0055_meme_operator6_desk"

_INSERT = (
    "INSERT INTO meme_treasury_swaps (id, reason, usdc_in, sol_out_quoted, sol_out_filled, "
    "  price_impact_pct, slippage_bps, signature, status, refusal, wallet_sol_before, "
    "  wallet_sol_after, input_mint, output_mint) "
    "VALUES (:id, :reason, :usdc_in, :sol_out_quoted, :sol_out_filled, "
    "  :price_impact_pct, :slippage_bps, :signature, :status, :refusal, :wallet_sol_before, "
    "  :wallet_sol_after, :input_mint, :output_mint)"
)

_TREASURY_ROW = {
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
    "input_mint": None,
    "output_mint": None,
}


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0056"))


@pytest.fixture(scope="module")
def upgraded(db_url: str) -> Iterator[str]:
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


async def _write_once(url: str, statement: str, params: dict[str, object]) -> None:
    created = async_engine(url)
    try:
        await _write(created, statement, params)
    finally:
        await created.dispose()


async def _clean_once(url: str) -> None:
    created = async_engine(url)
    try:
        await _clean(created)
    finally:
        await created.dispose()


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0056_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


@pytest.mark.asyncio
async def test_a_usdc_to_sol_treasury_row_keeps_both_columns_null(engine: AsyncEngine) -> None:
    await _write(engine, _INSERT, _TREASURY_ROW)
    try:
        async with engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT input_mint, output_mint FROM meme_treasury_swaps WHERE id = :id"
                        ),
                        {"id": _TREASURY_ROW["id"]},
                    )
                )
                .mappings()
                .first()
            )
        assert row is not None
        assert row["input_mint"] is None and row["output_mint"] is None
    finally:
        await _clean(engine)


@pytest.mark.asyncio
async def test_a_spot_swap_row_names_its_mint_pair(engine: AsyncEngine) -> None:
    row = {
        **_TREASURY_ROW,
        "id": str(uuid.uuid4()),
        "reason": "spot_swap:SOL->WIF",
        "input_mint": "So11111111111111111111111111111111111111112",
        "output_mint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    }
    await _write(engine, _INSERT, row)
    try:
        async with engine.connect() as connection:
            fetched = (
                (
                    await connection.execute(
                        text(
                            "SELECT input_mint, output_mint FROM meme_treasury_swaps WHERE id = :id"
                        ),
                        {"id": row["id"]},
                    )
                )
                .mappings()
                .first()
            )
        assert fetched is not None
        assert fetched["input_mint"] == row["input_mint"]
        assert fetched["output_mint"] == row["output_mint"]
    finally:
        await _clean(engine)


@pytest.mark.asyncio
async def test_one_mint_without_the_other_is_refused(engine: AsyncEngine) -> None:
    row = {
        **_TREASURY_ROW,
        "id": str(uuid.uuid4()),
        "input_mint": "So11111111111111111111111111111111111111112",
        "output_mint": None,
    }
    with pytest.raises(IntegrityError, match="mint_pair_is_named"):
        await _write(engine, _INSERT, row)


def test_the_downgrade_refuses_while_a_spot_swap_row_exists(db_url: str) -> None:
    config = alembic_config(db_url)
    command.upgrade(config, REVISION)
    row = {
        **_TREASURY_ROW,
        "id": str(uuid.uuid4()),
        "input_mint": "So11111111111111111111111111111111111111112",
        "output_mint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    }
    # One engine per ``asyncio.run``: an asyncpg connection pooled under a loop
    # that has since closed raises ``Event loop is closed`` on the next run.
    asyncio.run(_write_once(db_url, _INSERT, row))
    try:
        with pytest.raises(DBAPIError, match="spot swap mint pair"):
            command.downgrade(config, "-1")
    finally:
        asyncio.run(_clean_once(db_url))
    command.downgrade(config, "-1")
    assert asyncio.run(_revision_of(db_url)) == PREVIOUS
    command.upgrade(config, REVISION)


async def _revision_of(url: str) -> str | None:
    created = async_engine(url)
    try:
        async with created.connect() as connection:
            return await connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await created.dispose()
