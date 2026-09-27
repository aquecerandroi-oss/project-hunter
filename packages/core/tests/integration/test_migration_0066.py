"""``0066_meme_mature_opportunities`` (EXP-M26 R1): the chain and the slug; the
table is global (no RLS, no tenant column), append-only for the worker (``SELECT``
/``INSERT``, no ``UPDATE``/``DELETE``) and read-only for the app; one row per
``(rule_set_id, mint)``; the checks refuse a row without a proposal or a named
reason, a refusal reason without names, names beside a proposal, unknown labels,
a minute after the tick and a lane that started after the minute; the downgrade
refuses while a row exists (§17.7) and otherwise drops the table; ``alembic
check`` at head.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from hunter_core.domain.types import uuid7

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database, migration_ddl

pytestmark = pytest.mark.integration

REVISION = "0066_meme_mature_opportunities"
PREVIOUS = "0065_meme_pullback_control_arm"
TABLE = "meme_mature_opportunities"
RULE_SET = "01994d00-6c1a-7000-8000-000000000003"
"""``trendline_v0/1`` (``0026``): any seeded set satisfies the foreign key."""
_REVISION = "SELECT version_num FROM alembic_version"
MINUTE = datetime(2026, 10, 5, 12, 30, tzinfo=UTC)

_INSERT = (
    f"INSERT INTO {TABLE} (id, rule_set_id, mint, evaluated_at, features_end_time, "  # noqa: S608
    "  features_version, code_ref, inputs, gate, coverage_version, coverage_status, coverage, "
    "  proposal_refusals, proposal_id, no_proposal_reason, fidelity, lane_since) "
    "VALUES (:id, :rule_set, :mint, :evaluated_at, :end_time, 'meme_features_v3', 'abc123', "
    "  CAST(:inputs AS jsonb), CAST(:gate AS jsonb), 'v1', :coverage_status, "
    "  CAST(:coverage AS jsonb), CAST(:refusals AS text[]), :proposal, :reason, :fidelity, "
    "  :lane_since)"
)


def _params(**overrides: object) -> dict[str, object]:
    params: dict[str, object] = {
        "id": str(uuid7()),
        "rule_set": RULE_SET,
        "mint": "MATUREmint",
        "evaluated_at": MINUTE + timedelta(seconds=65),
        "end_time": MINUTE,
        "inputs": json.dumps({"mint": "MATUREmint"}),
        "gate": json.dumps([{"rule": "grafico_maduro/1"}]),
        "coverage_status": "covered",
        "coverage": json.dumps({"points": 16}),
        "refusals": ["creator_serial"],
        "proposal": None,
        "reason": "refused",
        "fidelity": "faithful",
        "lane_since": MINUTE - timedelta(minutes=3),
    }
    params.update(overrides)
    return params


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0066"))


@pytest.fixture(scope="module")
def upgraded(db_url: str) -> Iterator[str]:
    """This revision by name, not ``head`` (the ``0057`` argument)."""
    command.upgrade(alembic_config(db_url), REVISION)
    yield db_url


@pytest_asyncio.fixture
async def engine(upgraded: str) -> AsyncIterator[AsyncEngine]:
    created = async_engine(upgraded)
    try:
        yield created
    finally:
        await created.dispose()


async def _once[T](url: str, step: Callable[[AsyncEngine], Awaitable[T]]) -> T:
    created = async_engine(url)
    try:
        return await step(created)
    finally:
        await created.dispose()


async def _execute(engine: AsyncEngine, statement: str, params: dict[str, object]) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(statement), params)


async def _scalar(engine: AsyncEngine, statement: str) -> object:
    async with engine.connect() as connection:
        return await connection.scalar(text(statement))


def test_the_revision_lands_on_0065_and_fits_the_version_column() -> None:
    source = REPO_ROOT / "infra" / "migrations" / "versions" / f"{REVISION}.py"
    assert f'down_revision: str | None = "{PREVIOUS}"' in source.read_text(encoding="utf-8")
    assert len(REVISION) <= 32
    assert migration_ddl("meme_mature_opportunities").TABLE == TABLE


async def test_the_table_is_global_append_only_for_the_worker_and_read_only_for_the_app(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as connection:
        rls = await connection.scalar(
            text("SELECT relrowsecurity FROM pg_class WHERE relname = :t"), {"t": TABLE}
        )
        policies = await connection.scalar(
            text("SELECT count(*) FROM pg_policies WHERE tablename = :t"), {"t": TABLE}
        )
        tenant = await connection.scalar(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = 'organization_id'"
            ),
            {"t": TABLE},
        )
        grants = {
            (row[0], row[1])
            for row in await connection.execute(
                text(
                    "SELECT grantee, privilege_type FROM information_schema.role_table_grants "
                    "WHERE table_name = :t AND grantee IN ('hunter_app', 'hunter_worker')"
                ),
                {"t": TABLE},
            )
        }
        indexes = {
            row[0]
            for row in await connection.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": TABLE}
            )
        }
    assert (rls, policies, tenant) == (False, 0, 0)
    assert grants == {
        ("hunter_app", "SELECT"),
        ("hunter_worker", "SELECT"),
        ("hunter_worker", "INSERT"),
    }
    assert indexes == {
        f"pk_{TABLE}",
        f"uq_{TABLE}_rule_set_id",
        f"ix_{TABLE}_rule_set_evaluated_at",
        f"ix_{TABLE}_proposal_id",
    }


async def test_the_worker_cannot_rewrite_or_delete_a_first_opportunity(
    engine: AsyncEngine,
) -> None:
    params = _params(mint="ROLEmint")
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE hunter_worker"))
            await connection.execute(text(_INSERT), params)
        for statement in (
            f"UPDATE {TABLE} SET fidelity = 'write_failed' WHERE mint = 'ROLEmint'",  # noqa: S608
            f"DELETE FROM {TABLE} WHERE mint = 'ROLEmint'",  # noqa: S608
        ):
            with pytest.raises(DBAPIError, match="permission denied"):
                async with engine.begin() as connection:
                    await connection.execute(text("SET LOCAL ROLE hunter_worker"))
                    await connection.execute(text(statement))
    finally:
        await _execute(engine, f"DELETE FROM {TABLE} WHERE mint = 'ROLEmint'", {})  # noqa: S608


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"mint": ""}, "mint_not_blank"),
        ({"reason": None}, "a_proposal_or_a_reason"),
        ({"reason": "refused", "refusals": []}, "refused_iff_refusals_are_named"),
        ({"reason": "insert_failed"}, "refused_iff_refusals_are_named"),
        ({"reason": "forgot"}, "no_proposal_reason_is_known"),
        ({"coverage_status": "maybe"}, "coverage_status_is_a_known_label"),
        ({"fidelity": "probably"}, "fidelity_is_a_known_label"),
        ({"evaluated_at": MINUTE - timedelta(seconds=1)}, "the_minute_closed_before_the_tick"),
        ({"lane_since": MINUTE + timedelta(minutes=1)}, "the_lane_ran_before_the_minute"),
        ({"inputs": json.dumps([1])}, "inputs_is_an_object"),
        ({"gate": json.dumps({"rule": "x"})}, "gate_is_an_array"),
        ({"coverage": json.dumps([1])}, "coverage_is_an_object"),
    ],
)
async def test_the_checks_refuse_a_malformed_opportunity(
    engine: AsyncEngine, overrides: dict[str, object], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        await _execute(engine, _INSERT, _params(**overrides))


async def test_a_proposal_never_rides_with_refusals_and_must_exist(engine: AsyncEngine) -> None:
    with pytest.raises(IntegrityError, match="a_proposal_or_a_reason"):
        await _execute(engine, _INSERT, _params(proposal=str(uuid7())))
    with pytest.raises(IntegrityError, match="refused_iff_refusals_are_named"):
        await _execute(engine, _INSERT, _params(proposal=str(uuid7()), reason=None))
    with pytest.raises(IntegrityError, match="fk_meme_mature_opportunities_proposal_id"):
        await _execute(engine, _INSERT, _params(proposal=str(uuid7()), reason=None, refusals=[]))


async def test_one_row_per_rule_set_and_mint(engine: AsyncEngine) -> None:
    try:
        await _execute(engine, _INSERT, _params(mint="DUPmint"))
        later = _params(mint="DUPmint", end_time=MINUTE + timedelta(minutes=1))
        later["evaluated_at"] = MINUTE + timedelta(minutes=2)
        with pytest.raises(IntegrityError, match=f"uq_{TABLE}_rule_set_id"):
            await _execute(engine, _INSERT, later)
    finally:
        await _execute(engine, f"DELETE FROM {TABLE} WHERE mint = 'DUPmint'", {})  # noqa: S608


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    """``alembic check`` on a database of its own taken to ``head``."""
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0066_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


def test_the_downgrade_refuses_while_a_row_exists_and_otherwise_drops_the_table(
    upgraded: str,
) -> None:
    config = alembic_config(upgraded)
    asyncio.run(_once(upgraded, lambda e: _execute(e, _INSERT, _params(mint="KEEPmint"))))
    try:
        with pytest.raises(DBAPIError, match=f"1 {TABLE} rows exist"):
            command.downgrade(config, PREVIOUS)
        assert asyncio.run(_once(upgraded, lambda e: _scalar(e, _REVISION))) == REVISION
    finally:
        asyncio.run(_once(upgraded, lambda e: _execute(e, f"DELETE FROM {TABLE}", {})))  # noqa: S608
    command.downgrade(config, PREVIOUS)
    try:
        assert asyncio.run(_once(upgraded, lambda e: _scalar(e, _REVISION))) == PREVIOUS
        gone = f"SELECT to_regclass('public.{TABLE}') IS NULL"
        assert asyncio.run(_once(upgraded, lambda e: _scalar(e, gone))) is True
    finally:
        command.upgrade(config, REVISION)
    assert asyncio.run(_once(upgraded, lambda e: _scalar(e, _REVISION))) == REVISION
