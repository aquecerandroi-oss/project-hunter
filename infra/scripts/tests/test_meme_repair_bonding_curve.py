"""``meme_repair_bonding_curve.py`` against a real Postgres (T4.39/R36).

The fake-connection tests next door prove the SQL text; this one proves the
write-once trigger really does block a naive ``UPDATE meme_tokens SET
bonding_curve = ...`` and that the script's own DISABLE/ENABLE TRIGGER pair
gets past it — the one thing a fake connection cannot check.

Run: ``uv run pytest infra/scripts/tests/test_meme_repair_bonding_curve.py -q``
(needs Docker; skips cleanly when it is unreachable, same as
``test_create_partitions_integration.py``).
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

pytestmark = pytest.mark.integration

SCRIPTS_DIR = Path(__file__).resolve().parents[1]

# Real captured pump.fun mints (T4.1's ``pumpportal_ws_capture_raw.jsonl``) and
# the Mayhem program's shared ["sol-vault"] PDA that contaminated one of them
# (R36) — never a curve of anyone's. Real addresses so the base58/PDA
# derivation in the script under test has something genuine to decode; which
# mint plays which role here does not depend on the fixture file's own frames.
MINT_CONTAMINATED = "CGuNLUVmrers2FwnLjjVr9Tv8B726caZbRkY116Apump"
SOL_VAULT = "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"
MINT_ALREADY_CORRECT = "HTEqdy7kiWFTXrecd1UiMxtU53MP2o1Ybof7wLPBpump"
MINT_ALREADY_RECONCILED = "65STnXm42Srq78NNPkGAVUWKgB4zW8mRiNEVXkXFnXTv"

T0 = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def _load(name: str) -> ModuleType:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        f"hunter_infra_{name}_it", SCRIPTS_DIR / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def _run[T](url: str, work: Callable[[AsyncConnection], Awaitable[T]]) -> T:
    """One throwaway transaction per test: always rolled back, never committed —
    ``migrated_db_url`` is one session-scoped container shared by every test in
    this file (and the fixture's other users), and the mints below are reused
    verbatim across tests, which a commit would turn into primary-key
    collisions on the second test."""
    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                return await work(connection)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


_INSERT_TOKEN = text(
    "INSERT INTO meme_tokens (mint, bonding_curve, bonding_curve_raw, mayhem_enabled, "
    "  first_seen_source, first_seen_at, last_seen_at) "
    "VALUES (:mint, :bonding_curve, :bonding_curve_raw, :mayhem_enabled, "
    "  'pumpportal_ws', :t0, :t0)"
)


async def _seed(connection: AsyncConnection, pdas: ModuleType) -> None:
    await connection.execute(
        _INSERT_TOKEN,
        {
            "mint": MINT_CONTAMINATED,
            "bonding_curve": SOL_VAULT,
            "bonding_curve_raw": None,
            "mayhem_enabled": True,
            "t0": T0,
        },
    )
    await connection.execute(
        _INSERT_TOKEN,
        {
            "mint": MINT_ALREADY_CORRECT,
            "bonding_curve": pdas.bonding_curve_address(MINT_ALREADY_CORRECT),
            "bonding_curve_raw": None,
            "mayhem_enabled": True,
            "t0": T0,
        },
    )
    await connection.execute(
        _INSERT_TOKEN,
        {
            "mint": MINT_ALREADY_RECONCILED,
            "bonding_curve": pdas.bonding_curve_address(MINT_ALREADY_RECONCILED),
            "bonding_curve_raw": SOL_VAULT,
            "mayhem_enabled": True,
            "t0": T0,
        },
    )


async def _row(connection: AsyncConnection, mint: str) -> dict[str, object]:
    result = await connection.execute(
        text("SELECT bonding_curve, bonding_curve_raw FROM meme_tokens WHERE mint = :mint"),
        {"mint": mint},
    )
    mapping = result.mappings().one()
    return dict(mapping)


def test_dry_run_finds_only_the_contaminated_row_and_writes_nothing(migrated_db_url: str) -> None:
    script = _load("meme_repair_bonding_curve")

    async def _work(connection: AsyncConnection) -> None:
        from hunter_exchanges.pumpfun import pdas as real_pdas

        await _seed(connection, real_pdas)
        found = await script.candidates(connection, limit=None)
        assert [c.mint for c in found] == [MINT_CONTAMINATED]
        assert found[0].derived == real_pdas.bonding_curve_address(MINT_CONTAMINATED)
        code, report = await script.run(connection, limit=None, apply=False, reason=None)
        assert code == 0 and "dry-run" in report and "1 candidate" in report
        row = await _row(connection, MINT_CONTAMINATED)
        assert row["bonding_curve"] == SOL_VAULT, "dry-run must not touch the row"
        assert row["bonding_curve_raw"] is None

    asyncio.run(_run(migrated_db_url, _work))


def test_a_naive_update_is_blocked_by_the_write_once_trigger(migrated_db_url: str) -> None:
    """Proves the trigger is really there before proving the script gets past it."""

    async def _work(connection: AsyncConnection) -> None:
        from hunter_exchanges.pumpfun import pdas as real_pdas

        await _seed(connection, real_pdas)
        with pytest.raises(Exception, match="written once"):
            await connection.execute(
                text("UPDATE meme_tokens SET bonding_curve = 'x' WHERE mint = :mint"),
                {"mint": MINT_CONTAMINATED},
            )

    asyncio.run(_run(migrated_db_url, _work))


def test_apply_repairs_the_contaminated_row_keeps_the_raw_and_leaves_the_others_alone(
    migrated_db_url: str,
) -> None:
    script = _load("meme_repair_bonding_curve")

    async def _work(connection: AsyncConnection) -> None:
        from hunter_exchanges.pumpfun import pdas as real_pdas

        await _seed(connection, real_pdas)
        code, report = await script.run(
            connection,
            limit=None,
            apply=True,
            reason="T4.39: mayhem create frame carried the shared sol-vault",
        )
        assert code == 0 and "applied: 1 row(s)" in report
        assert "mayhem_enabled=true: 1, false: 0" in report

        repaired = await _row(connection, MINT_CONTAMINATED)
        assert repaired["bonding_curve"] == real_pdas.bonding_curve_address(MINT_CONTAMINATED)
        assert repaired["bonding_curve_raw"] == SOL_VAULT

        untouched = await _row(connection, MINT_ALREADY_CORRECT)
        assert untouched["bonding_curve"] == real_pdas.bonding_curve_address(MINT_ALREADY_CORRECT)
        assert untouched["bonding_curve_raw"] is None

        already_done = await _row(connection, MINT_ALREADY_RECONCILED)
        assert already_done["bonding_curve_raw"] == SOL_VAULT, "not touched a second time"

        audit = await connection.execute(
            text(
                "SELECT message FROM system_events WHERE component = :c ORDER BY created_at DESC LIMIT 1"
            ),
            {"c": script.COMPONENT},
        )
        message = audit.scalar_one()
        assert "repaired 1" in message and "mayhem_enabled=true: 1" in message

        # write-once trigger is back on: a second, naive UPDATE is refused again
        with pytest.raises(Exception, match="written once"):
            await connection.execute(
                text("UPDATE meme_tokens SET bonding_curve = 'y' WHERE mint = :mint"),
                {"mint": MINT_CONTAMINATED},
            )

    asyncio.run(_run(migrated_db_url, _work))


def test_running_apply_again_finds_nothing_left_to_do(migrated_db_url: str) -> None:
    script = _load("meme_repair_bonding_curve")

    async def _work(connection: AsyncConnection) -> None:
        from hunter_exchanges.pumpfun import pdas as real_pdas

        await _seed(connection, real_pdas)
        await script.run(
            connection, limit=None, apply=True, reason="T4.39: first pass repairs everything"
        )
        code, report = await script.run(
            connection, limit=None, apply=True, reason="T4.39: second pass finds nothing"
        )
        assert code == 0 and "nothing to do" in report

    asyncio.run(_run(migrated_db_url, _work))
