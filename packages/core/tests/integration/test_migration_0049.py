"""``0049_meme_gate_buyers25_arm`` (T4.48) — its own file and its own database.

A new file, in ``test_migration_0048.py``'s shape, because ``test_migrations.py``
is being edited by other tasks while this revision is written; the two lines this
revision owes that file (``HEAD_REVISION`` and ``0022``'s active-set count, 15 →
16) are changed there too, and nothing here depends on them.

What is proved: the seed exists with ``min_unique_buyers = 25`` under EXP-M10 on
the 15-second clock; it is ``flow_v2/6`` with that **one** key moved and every
other param byte for byte identical; it is paper by construction (``kind =
'research_only'``, and the executor only ever opens proposals of an ``operator``
set); the downgrade removes it on a clean database and refuses while a proposal
or a bet references it (§17.7).
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

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database

pytestmark = pytest.mark.integration

REVISION = "0049_meme_gate_buyers25_arm"
PREVIOUS = "0048_meme_creator_initial_buy"

BUYERS25_RULE_SET = "01994d00-6c1a-7000-8000-000000000014"
E2B_RULE_SET = "01994d00-6c1a-7000-8000-000000000013"
"""``flow_v2/6`` (``0044``) — this arm's base **and** its control."""

_A_PROPOSAL = (
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at, "
    "  decision, decided_by, decided_at) VALUES (:id, 'GUARD_MINT_49', :rule_set, 'operator', "
    "  'approved', now() + interval '2 minutes', '{}'::jsonb, 'user', now())"
)
_A_BET = (
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, entry_at, entry, "
    "  initial_risk_sol, params) VALUES (:id, :proposal, :rule_set, 'GUARD_MINT_49', 'paper', "
    "  now(), '{}'::jsonb, 0.05, '{}'::jsonb)"
)
_CLEAN: tuple[str, ...] = (
    "DELETE FROM meme_paper_bets WHERE mint = 'GUARD_MINT_49'",
    "DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT_49'",
)


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0049"))


@pytest.fixture(scope="module")
def upgraded(db_url: str) -> Iterator[str]:
    """This revision by name, not ``head`` (T4.71: ``0055`` seeds a second active
    ``operator`` set, so "the desk is ``operator/5`` alone" is true **at** this
    revision and false at the head — the shape ``0050``+ already use)."""
    command.upgrade(alembic_config(db_url), REVISION)
    yield db_url


@pytest_asyncio.fixture
async def engine(upgraded: str) -> AsyncIterator[AsyncEngine]:
    created = async_engine(upgraded)
    try:
        yield created
    finally:
        await created.dispose()


async def _write(url: str, statements: list[tuple[str, dict[str, object]]]) -> None:
    """Run statements as the owner, each with its own parameters."""
    created = async_engine(url)
    try:
        async with created.begin() as connection:
            for statement, parameters in statements:
                await connection.execute(text(statement), parameters)
    finally:
        await created.dispose()


async def _revision_of(url: str) -> str | None:
    created = async_engine(url)
    try:
        async with created.connect() as connection:
            return await connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await created.dispose()


def test_the_revision_lands_on_0048() -> None:
    """Pure: no database, no container — the chain this task was told to extend.

    Read as text, like ``0048``'s twin: importing the module would execute the
    ``from ddl...`` imports that only resolve with ``infra/migrations`` on the
    path, and this assertion is about two literals."""
    source = (REPO_ROOT / "infra" / "migrations" / "versions" / f"{REVISION}.py").read_text(
        encoding="utf-8"
    )
    assert f'revision: str = "{REVISION}"' in source
    assert f'down_revision: str | None = "{PREVIOUS}"' in source


def test_only_an_operator_set_reaches_the_executor_so_a_research_arm_is_paper() -> None:
    """Why ``kind = 'research_only'`` *is* the paper flag, read from the executor
    rather than assumed: ``auto_approve`` selects proposals of an **operator**
    set, so no ``research_only`` arm can ever be opened on money."""
    source = (
        REPO_ROOT / "services" / "meme-executor" / "hunter_meme_executor" / "auto_approve.py"
    ).read_text(encoding="utf-8")
    assert "\"WHERE rs.kind = 'operator' AND rs.status = 'active' \"" in source


@pytest.mark.asyncio
async def test_the_arm_is_seeded_with_the_floor_of_25(engine: AsyncEngine) -> None:
    """``flow_v2/7``: ``research_only`` under EXP-M10, active, 15-second clock,
    ``min_unique_buyers = 25`` — the floor KB-0114 measured at +0,090 R."""
    async with engine.connect() as connection:
        seeded = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT name || '/' || version || ':' || kind || ':' "
                    "|| coalesce(exp_ref, '-') || ':' || status || ':' "
                    "|| (params ->> 'min_unique_buyers') || ':' || (params ->> 'clock') "
                    "|| ':' || (params ->> 'gate_key') || '/' || (params ->> 'gate_version') "
                    "|| ':' || (params ->> 'size_sol') || ':' || (params ->> 'target_x') "
                    "|| ':' || (params ->> 'max_participation_pct') "
                    "|| ':' || (params ->> 'min_holders') "
                    "FROM meme_rule_sets WHERE id = :b"
                ),
                {"b": BUYERS25_RULE_SET},
            )
        ]
    assert seeded == [
        "flow_v2/7:research_only:EXP-M10:active:25:15s:fluxo_e_holders/3:0.05:3:1:20"
    ], (
        "the pre-registration freezes the exits, the size, the 1 % participation cap and "
        "min_holders = 20 as the control's — only the floor of buyers moves"
    )


@pytest.mark.asyncio
async def test_the_arm_is_flow_v2_6_with_exactly_one_number_moved(engine: AsyncEngine) -> None:
    """The whole experiment, as an assertion: drop ``min_unique_buyers`` from
    both sets and they are the same object. Anything else that moved would make
    the Δ R of EXP-M10 unattributable."""
    async with engine.connect() as connection:
        rows = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT ((b.params - 'min_unique_buyers') = (e.params - 'min_unique_buyers'))"
                    "  ::text || ':' || (b.params ->> 'min_unique_buyers') "
                    "|| ':' || (e.params ->> 'min_unique_buyers') "
                    "FROM meme_rule_sets b, meme_rule_sets e WHERE b.id = :b AND e.id = :e"
                ),
                {"b": BUYERS25_RULE_SET, "e": E2B_RULE_SET},
            )
        ]
    assert rows == ["true:25:10"], "flow_v2/7 minus the floor is flow_v2/6, byte for byte"


@pytest.mark.asyncio
async def test_the_desk_is_untouched_and_the_control_stays_active(engine: AsyncEngine) -> None:
    """``flow_v2/6`` keeps running beside the arm (the comparison is the point)
    and the desk keeps exactly one ``operator`` set: the floor of 25 never fires
    on money."""
    async with engine.connect() as connection:
        control = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT name || '/' || version || ':' || status FROM meme_rule_sets "
                    "WHERE id = :e"
                ),
                {"e": E2B_RULE_SET},
            )
        ]
        desk = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT name || '/' || version FROM meme_rule_sets "
                    "WHERE kind = 'operator' AND status = 'active' ORDER BY version"
                )
            )
        ]
    assert control == ["flow_v2/6:active"]
    assert desk == ["operator/5"]


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    """``alembic check`` on a database of its own taken all the way to ``head``
    (this module's own database is staged at ``REVISION``, where the models —
    which describe the head — would legitimately differ): this revision seeds
    data and changes no schema, so the comparison must still find nothing."""
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0049_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


def test_the_downgrade_refuses_while_a_proposal_or_a_bet_references_the_arm(
    upgraded: str,
) -> None:
    """§17.7: a proposal or a bet under ``flow_v2/7`` is evidence of the
    experiment — count, name, stop."""
    config = alembic_config(upgraded)
    # T4.49: staged at ``0049`` first — ``0050_meme_gate_ratio10_arm`` sits on
    # top, so ``"-1"`` from the head reverses *that* seed, not this revision.
    command.downgrade(config, REVISION)
    proposal = "00000000-0000-4000-8000-000000004901"
    bet = "00000000-0000-4000-8000-000000004902"
    guarded: list[tuple[list[tuple[str, dict[str, object]]], str]] = [
        (
            [(_A_PROPOSAL, {"id": proposal, "rule_set": BUYERS25_RULE_SET})],
            "proposals reference the seeded flow_v2/7 set",
        ),
        (
            [
                (_A_PROPOSAL, {"id": proposal, "rule_set": E2B_RULE_SET}),
                (
                    _A_BET,
                    {"id": bet, "proposal": proposal, "rule_set": BUYERS25_RULE_SET},
                ),
            ],
            "bets reference the seeded flow_v2/7 set",
        ),
    ]
    try:
        for statements, message in guarded:
            asyncio.run(_write(upgraded, statements))
            try:
                with pytest.raises(DBAPIError, match=message):
                    command.downgrade(config, "-1")
                assert asyncio.run(_revision_of(upgraded)) == REVISION, (
                    "the downgrade must not commit"
                )
            finally:
                asyncio.run(_write(upgraded, [(statement, {}) for statement in _CLEAN]))
    finally:
        command.upgrade(config, "head")


def test_the_downgrade_removes_the_seed_on_a_clean_database_and_comes_back(
    upgraded: str,
) -> None:
    """The arm goes and comes back; the control and the desk do not move."""
    config = alembic_config(upgraded)
    # T4.49: the same staging as the guard test above — ``"-1"`` stopped meaning
    # ``0049`` the day ``0050`` landed on top.
    command.downgrade(config, REVISION)
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_revision_of(upgraded)) == PREVIOUS
        assert asyncio.run(_count_of(upgraded, BUYERS25_RULE_SET)) == 0, (
            "the seed is the whole revision: reversing it leaves no row behind"
        )
        assert asyncio.run(_count_of(upgraded, E2B_RULE_SET)) == 1
    finally:
        command.upgrade(config, "head")
    # The head is ``0050`` since T4.49, so what is asserted here is "back above
    # this revision", not "back at it".
    assert asyncio.run(_revision_of(upgraded)) != PREVIOUS
    assert asyncio.run(_count_of(upgraded, BUYERS25_RULE_SET)) == 1
    command.check(config)


async def _count_of(url: str, rule_set: str) -> int:
    created = async_engine(url)
    try:
        async with created.connect() as connection:
            found = await connection.scalar(
                text("SELECT count(*) FROM meme_rule_sets WHERE id = :r"), {"r": rule_set}
            )
            return int(found or 0)
    finally:
        await created.dispose()
