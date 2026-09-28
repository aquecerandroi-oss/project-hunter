"""``0068_meme_wallet_exceptions`` (F1, decision 2026-09-28) — its own database.

What is proved: the table is global (no RLS, no tenant column) and **read-only
for both roles** (``SELECT`` only — the owner's audited CLI is the only writer);
a row is never deleted nor truncated, and the only change it ever takes is one
whole revocation that leaves every original column unchanged (triggers, which
hold the owner too); at most one active exception per (wallet, mint), a revoked
one frees the slot; the named checks refuse a stranger program and a note
outside ``obsidian/``; the downgrade refuses while **any** row exists (revoked
included) and otherwise removes table, triggers and function; the held EXP-M26
seed now lands on this revision; ``alembic check`` at head.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database, migration_ddl

pytestmark = pytest.mark.integration

REVISION = "0068_meme_wallet_exceptions"
PREVIOUS = "0067_meme_token_state_history"
SEED = "0069_meme_mature_chart_arms"
TABLE = "meme_wallet_holding_exceptions"
WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
MINT = "DgY9Z8xPG1346Ydrq98ASAZcVdyrurT4tCQ7TDapHcJg"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
_REVISION = "SELECT version_num FROM alembic_version"
_INSERT = (
    f"INSERT INTO {TABLE} (id, wallet, token_program, mint, max_atoms, decimals, "  # noqa: S608
    "require_frozen, evidence, reason, note_path, note_sha256, created_by) VALUES (:id, :wallet, "
    ":program, :mint, CAST(:atoms AS numeric), 6, true, CAST(:evidence AS jsonb), "
    "'token de phishing congelado pelo emissor', :note, :sha, 'Everton')"
)
_REVOKE = (
    f"UPDATE {TABLE} SET revoked_at = now(), revoked_by = 'Everton', "  # noqa: S608
    "revoke_reason = 'o emissor descongelou a conta' WHERE id = :id"
)
_FORGET = (
    f"ALTER TABLE {TABLE} DISABLE TRIGGER USER",
    f"DELETE FROM {TABLE}",  # noqa: S608
    f"ALTER TABLE {TABLE} ENABLE TRIGGER USER",
)
"""The test's own cleanup, as the owner, with the guard explicitly switched off."""


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_wallet_exc"))


@pytest.fixture(scope="module")
def upgraded(db_url: str) -> Iterator[str]:
    """This revision by name, not ``head``."""
    command.upgrade(alembic_config(db_url), REVISION)
    yield db_url


@pytest_asyncio.fixture
async def engine(upgraded: str) -> AsyncIterator[AsyncEngine]:
    created = async_engine(upgraded)
    try:
        yield created
    finally:
        async with created.begin() as connection:
            for statement in _FORGET:
                await connection.execute(text(statement))
        await created.dispose()


async def _once[R](url: str, step: Callable[[AsyncEngine], Awaitable[R]]) -> R:
    created = async_engine(url)
    try:
        return await step(created)
    finally:
        await created.dispose()


def _row(**overrides: Any) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "wallet": WALLET,
        "program": TOKEN_2022,
        "mint": MINT,
        "evidence": json.dumps({"accounts": [{"state": "frozen"}]}),
        "note": "obsidian/06-DECISIONS/2026-09-28-excecao-auditada-token-golpe.md",
        "sha": "a" * 64,
        "atoms": "100000000000",
        **overrides,
    }


async def _exec(engine: AsyncEngine, statement: str, params: dict[str, Any] | None = None) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(statement), params or {})


async def _scalar(engine: AsyncEngine, statement: str, params: dict[str, Any] | None = None) -> Any:
    async with engine.connect() as connection:
        return await connection.scalar(text(statement), params or {})


def test_the_revision_lands_on_0067_and_the_held_seed_on_it() -> None:
    """The seed half is conditional (database-architect review, must-fix 1): the
    wallet commit ships without ``0069``, and this same file must hold in both."""
    versions = REPO_ROOT / "infra" / "migrations" / "versions"
    source = (versions / f"{REVISION}.py").read_text(encoding="utf-8")
    assert f'down_revision: str | None = "{PREVIOUS}"' in source
    assert not (versions / "0068_meme_mature_chart_arms.py").exists()
    assert len(REVISION) <= 32 and len(SEED) <= 32
    assert migration_ddl("meme_wallet_exceptions").TABLE == TABLE
    seed = versions / f"{SEED}.py"
    if seed.exists():
        assert f'down_revision: str | None = "{REVISION}"' in seed.read_text(encoding="utf-8")


async def test_the_table_is_global_and_read_only_for_both_roles(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        rls = await connection.scalar(
            text("SELECT relrowsecurity FROM pg_class WHERE relname = :t"), {"t": TABLE}
        )
        tenant = await connection.scalar(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = 'organization_id'"
            ),
            {"t": TABLE},
        )
        held = {
            (role, privilege)
            for role in ("hunter_app", "hunter_worker", "hunter_runtime")
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
            if await connection.scalar(
                text("SELECT has_table_privilege(:r, :t, :p)"),
                {"r": role, "t": TABLE, "p": privilege},
            )
        }
    assert rls is False and tenant == 0
    assert held == {("hunter_app", "SELECT"), ("hunter_worker", "SELECT")}


async def test_the_worker_cannot_write_an_exception(engine: AsyncEngine) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE hunter_worker"))
            await connection.execute(text(_INSERT), _row())


async def test_a_row_is_never_deleted_nor_truncated(engine: AsyncEngine) -> None:
    row = _row()
    await _exec(engine, _INSERT, row)
    with pytest.raises(DBAPIError, match="is never deleted"):
        await _exec(engine, f"DELETE FROM {TABLE} WHERE id = :id", {"id": row["id"]})  # noqa: S608
    with pytest.raises(DBAPIError, match="is never deleted"):
        await _exec(engine, f"TRUNCATE {TABLE}")
    assert await _scalar(engine, f"SELECT count(*) FROM {TABLE}") == 1  # noqa: S608


async def test_the_only_change_is_one_whole_revocation(engine: AsyncEngine) -> None:
    row = _row()
    await _exec(engine, _INSERT, row)
    with pytest.raises(DBAPIError, match="only change an exception takes"):
        await _exec(engine, f"UPDATE {TABLE} SET max_atoms = 1 WHERE id = :id", {"id": row["id"]})  # noqa: S608
    with pytest.raises(DBAPIError, match="leaves every original column unchanged"):
        await _exec(
            engine,
            _REVOKE.replace("WHERE", ", reason = 'outra razao qualquer' WHERE"),
            {"id": row["id"]},
        )
    with pytest.raises(DBAPIError, match="a_revocation_is_whole"):
        await _exec(
            engine,
            f"UPDATE {TABLE} SET revoked_at = now() WHERE id = :id",  # noqa: S608
            {"id": row["id"]},
        )
    await _exec(engine, _REVOKE, {"id": row["id"]})
    with pytest.raises(DBAPIError, match="already revoked"):
        await _exec(engine, _REVOKE, {"id": row["id"]})
    with pytest.raises(DBAPIError, match="already revoked"):
        await _exec(
            engine,
            f"UPDATE {TABLE} SET revoked_at = NULL, revoked_by = NULL, revoke_reason = NULL "  # noqa: S608
            "WHERE id = :id",
            {"id": row["id"]},
        )


async def test_one_active_exception_per_wallet_and_mint(engine: AsyncEngine) -> None:
    first = _row()
    await _exec(engine, _INSERT, first)
    with pytest.raises(DBAPIError, match="ux_meme_wallet_holding_exceptions_active"):
        await _exec(engine, _INSERT, _row())
    await _exec(engine, _INSERT, _row(wallet="Other1111111111111111111111111111111111111"))
    await _exec(engine, _REVOKE, {"id": first["id"]})
    await _exec(engine, _INSERT, _row())  # a revoked row frees the slot
    active = f"SELECT count(*) FROM {TABLE} WHERE revoked_at IS NULL"  # noqa: S608
    assert await _scalar(engine, active) == 2


async def test_u64_max_is_accepted(engine: AsyncEngine) -> None:
    await _exec(engine, _INSERT, _row(atoms="18446744073709551615"))


async def test_the_database_stamps_the_creation_whatever_the_writer_says(
    engine: AsyncEngine,
) -> None:
    """Database-architect review (D): ``created_at`` is the database's ``now()``,
    never a backdated value a writer passes."""
    row = _row()
    backdated = _INSERT.replace("created_by)", "created_by, created_at)").replace(
        "'Everton')", "'Everton', '2026-01-01T00:00:00Z')"
    )
    async with engine.begin() as connection:
        await connection.execute(text(backdated), row)
        stamped = await connection.scalar(
            text(f"SELECT created_at = now() FROM {TABLE} WHERE id = :id"),  # noqa: S608
            {"id": row["id"]},
        )
    assert stamped is True


async def test_a_row_is_never_born_revoked(engine: AsyncEngine) -> None:
    pre_revoked = _INSERT.replace(
        "created_by)", "created_by, revoked_at, revoked_by, revoke_reason)"
    ).replace("'Everton')", "'Everton', now(), 'Everton', 'nasceu revogada de proposito')")
    with pytest.raises(DBAPIError, match="is born active"):
        await _exec(engine, pre_revoked, _row())
    assert await _scalar(engine, f"SELECT count(*) FROM {TABLE}") == 0  # noqa: S608


@pytest.mark.parametrize("when", ["now() + interval '1 day'", "now() - interval '1 second'"])
async def test_a_revocation_is_stamped_now(engine: AsyncEngine, when: str) -> None:
    row = _row()
    await _exec(engine, _INSERT, row)
    with pytest.raises(DBAPIError, match="a revocation is stamped by the database"):
        await _exec(engine, _REVOKE.replace("revoked_at = now()", f"revoked_at = {when}"), row)


@pytest.mark.parametrize(
    ("override", "constraint"),
    [
        ({"program": "11111111111111111111111111111111"}, "program_is_a_token_program"),
        ({"note": "docs/RISK_ENGINE_MEME.md"}, "note_is_under_obsidian"),
        ({"note": "obsidian/nota.txt"}, "note_is_under_obsidian"),
        ({"sha": "abc"}, "note_is_under_obsidian"),
        ({"mint": ""}, "identity_is_well_formed"),
        ({"evidence": "[]"}, "evidence_is_an_object"),
        ({"atoms": "NaN"}, "atoms_fit_a_u64"),  # NaN sorts above every number
        ({"atoms": "18446744073709551616"}, "atoms_fit_a_u64"),  # u64 max + 1
        ({"atoms": "0"}, "atoms_fit_a_u64"),
    ],
)
async def test_the_named_checks_refuse_a_malformed_exception(
    engine: AsyncEngine, override: dict[str, str], constraint: str
) -> None:
    with pytest.raises(DBAPIError, match=constraint):
        await _exec(engine, _INSERT, _row(**override))


def test_the_downgrade_refuses_while_any_row_exists_and_otherwise_removes_everything(
    upgraded: str,
) -> None:
    config = alembic_config(upgraded)

    async def plant_revoked(engine: AsyncEngine) -> None:
        row = _row()
        await _exec(engine, _INSERT, row)
        await _exec(engine, _REVOKE, {"id": row["id"]})

    async def forget(engine: AsyncEngine) -> None:
        async with engine.begin() as connection:
            for statement in _FORGET:
                await connection.execute(text(statement))

    asyncio.run(_once(upgraded, plant_revoked))
    try:
        with pytest.raises(DBAPIError, match=f"1 {TABLE} rows exist"):
            command.downgrade(config, PREVIOUS)
        assert asyncio.run(_once(upgraded, lambda e: _scalar(e, _REVISION))) == REVISION
    finally:
        asyncio.run(_once(upgraded, forget))
    command.downgrade(config, PREVIOUS)
    try:
        assert asyncio.run(_once(upgraded, lambda e: _scalar(e, _REVISION))) == PREVIOUS
        leftovers = (
            f"SELECT (to_regclass('public.{TABLE}') IS NULL) "  # noqa: S608 - a constant
            "AND NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname LIKE 'meme_wallet_holding%') "
            "AND NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname LIKE 'meme_wallet_holding%')"
        )
        assert asyncio.run(_once(upgraded, lambda e: _scalar(e, leftovers))) is True
    finally:
        command.upgrade(config, REVISION)
    assert asyncio.run(_once(upgraded, lambda e: _scalar(e, _REVISION))) == REVISION


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    """``alembic check`` on a database of its own taken to ``head``."""
    db_url = asyncio.run(create_database(container_url, "hunter_migration_wallet_exc_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)
