"""``0050_meme_gate_ratio10_arm`` (T4.49) — its own file and its own database.

A new file, in ``test_migration_0049.py``'s shape, because ``test_migrations.py``
is being edited by other tasks while this revision is written; the two lines this
revision owes that file (``HEAD_REVISION`` and ``0022``'s active-set count, 16 →
17) are changed there too, and nothing here depends on them.

What is proved: the seed exists with ``max_sells_to_buys = "1.0"`` under EXP-M14
on the 15-second clock; it is ``flow_v2/6`` with that **one** key moved and every
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

REVISION = "0050_meme_gate_ratio10_arm"
PREVIOUS = "0049_meme_gate_buyers25_arm"

RATIO10_RULE_SET = "01994d00-6c1a-7000-8000-000000000015"
E2B_RULE_SET = "01994d00-6c1a-7000-8000-000000000013"
"""``flow_v2/6`` (``0044``) — this arm's base **and** its control."""

RATIO_KEY = "max_sells_to_buys"
"""The key ``flow_v2/6`` really carries. EXP-M14's page names it
``max_sell_buy_ratio`` (the feature column's name); moving *that* would have
seeded a param nothing reads. Declared here, in the DDL module and in the page."""

_A_PROPOSAL = (
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at, "
    "  decision, decided_by, decided_at) VALUES (:id, 'GUARD_MINT_50', :rule_set, 'operator', "
    "  'approved', now() + interval '2 minutes', '{}'::jsonb, 'user', now())"
)
_A_BET = (
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, entry_at, entry, "
    "  initial_risk_sol, params) VALUES (:id, :proposal, :rule_set, 'GUARD_MINT_50', 'paper', "
    "  now(), '{}'::jsonb, 0.05, '{}'::jsonb)"
)
_CLEAN: tuple[str, ...] = (
    "DELETE FROM meme_paper_bets WHERE mint = 'GUARD_MINT_50'",
    "DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT_50'",
)


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0050"))


@pytest.fixture(scope="module")
def upgraded(db_url: str) -> Iterator[str]:
    """This revision, not ``head``: ``0051`` (T4.54) now lands on top of it, and
    this module's downgrade assertions (``"-1"`` -> ``PREVIOUS``) are about the
    one step this revision itself takes, not about whatever the chain grows to
    after it."""
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


def test_the_revision_lands_on_0049() -> None:
    """Pure: no database, no container — the chain this task was told to extend.

    Read as text, like ``0049``'s twin: importing the module would execute the
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
async def test_the_arm_is_seeded_with_the_ceiling_of_one(engine: AsyncEngine) -> None:
    """``flow_v2/8``: ``research_only`` under EXP-M14, active, 15-second clock,
    ``max_sells_to_buys = "1.0"`` — the ceiling R48 measured at the peak of the
    graduation rate. The value is a string, like every decimal in these params."""
    async with engine.connect() as connection:
        seeded = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT name || '/' || version || ':' || kind || ':' "  # noqa: S608
                    "|| coalesce(exp_ref, '-') || ':' || status || ':' "
                    f"|| (params ->> '{RATIO_KEY}') || ':' || (params ->> 'clock') "
                    "|| ':' || (params ->> 'gate_key') || '/' || (params ->> 'gate_version') "
                    "|| ':' || (params ->> 'size_sol') || ':' || (params ->> 'target_x') "
                    "|| ':' || (params ->> 'max_participation_pct') "
                    "|| ':' || (params ->> 'min_holders') "
                    "|| ':' || (params ->> 'min_unique_buyers') "
                    f"|| ':' || jsonb_typeof(params -> '{RATIO_KEY}') "
                    "FROM meme_rule_sets WHERE id = :r"
                ),
                {"r": RATIO10_RULE_SET},
            )
        ]
    assert seeded == [
        "flow_v2/8:research_only:EXP-M14:active:1.0:15s:fluxo_e_holders/3:0.05:3:1:20:10:string"
    ], (
        "the pre-registration freezes the exits, the size, the 1 % participation cap, "
        "min_holders = 20 and the floor of 10 buyers as the control's — only the "
        "sells/buys ceiling moves"
    )


@pytest.mark.asyncio
async def test_the_arm_is_flow_v2_6_with_exactly_one_number_moved(engine: AsyncEngine) -> None:
    """The whole experiment, as an assertion: drop ``max_sells_to_buys`` from
    both sets and they are the same object. Anything else that moved would make
    the Δ R of EXP-M14 unattributable."""
    async with engine.connect() as connection:
        rows = [
            row[0]
            for row in await connection.execute(
                text(
                    f"SELECT ((r.params - '{RATIO_KEY}') = (e.params - '{RATIO_KEY}'))"  # noqa: S608
                    f"  ::text || ':' || (r.params ->> '{RATIO_KEY}') "
                    f"|| ':' || (e.params ->> '{RATIO_KEY}') "
                    "FROM meme_rule_sets r, meme_rule_sets e WHERE r.id = :r AND e.id = :e"
                ),
                {"r": RATIO10_RULE_SET, "e": E2B_RULE_SET},
            )
        ]
    assert rows == ["true:1.0:0.6"], "flow_v2/8 minus the ceiling is flow_v2/6, byte for byte"


@pytest.mark.asyncio
async def test_the_desk_is_untouched_and_the_control_stays_active(engine: AsyncEngine) -> None:
    """``flow_v2/6`` keeps running beside the arm (the comparison is the point)
    and the desk keeps exactly one ``operator`` set: the ceiling of 1,0 never
    fires on money."""
    async with engine.connect() as connection:
        control = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT name || '/' || version || ':' || status || ':' "  # noqa: S608
                    f"|| (params ->> '{RATIO_KEY}') FROM meme_rule_sets "
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
    assert control == ["flow_v2/6:active:0.6"]
    assert desk == ["operator/5"]


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    """``alembic check`` needs the true head, not just this revision — ``0051``
    (T4.54) lands on top of ``0050`` and adds a table of its own, so this
    assertion runs on its own database taken all the way to ``head`` rather
    than on ``upgraded`` (staged at ``REVISION`` for the downgrade tests
    below): this revision itself still seeds data and changes no schema, the
    same assertion the ``0049`` tests make around their own seed."""
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0050_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


def test_the_downgrade_refuses_while_a_proposal_or_a_bet_references_the_arm(
    upgraded: str,
) -> None:
    """§17.7: a proposal or a bet under ``flow_v2/8`` is evidence of the
    experiment — count, name, stop. ``"-1"`` means this revision while it is the
    head; the day another lands on top, stage at ``REVISION`` first."""
    config = alembic_config(upgraded)
    proposal = "00000000-0000-4000-8000-000000005001"
    bet = "00000000-0000-4000-8000-000000005002"
    guarded: list[tuple[list[tuple[str, dict[str, object]]], str]] = [
        (
            [(_A_PROPOSAL, {"id": proposal, "rule_set": RATIO10_RULE_SET})],
            "proposals reference the seeded flow_v2/8 set",
        ),
        (
            [
                (_A_PROPOSAL, {"id": proposal, "rule_set": E2B_RULE_SET}),
                (
                    _A_BET,
                    {"id": bet, "proposal": proposal, "rule_set": RATIO10_RULE_SET},
                ),
            ],
            "bets reference the seeded flow_v2/8 set",
        ),
    ]
    for statements, message in guarded:
        asyncio.run(_write(upgraded, statements))
        try:
            with pytest.raises(DBAPIError, match=message):
                command.downgrade(config, "-1")
            assert asyncio.run(_revision_of(upgraded)) == REVISION, "the downgrade must not commit"
        finally:
            asyncio.run(_write(upgraded, [(statement, {}) for statement in _CLEAN]))


def test_the_downgrade_removes_the_seed_on_a_clean_database_and_comes_back(
    upgraded: str,
) -> None:
    """The arm goes and comes back; the control and the desk do not move."""
    config = alembic_config(upgraded)
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_revision_of(upgraded)) == PREVIOUS
        assert asyncio.run(_count_of(upgraded, RATIO10_RULE_SET)) == 0, (
            "the seed is the whole revision: reversing it leaves no row behind"
        )
        assert asyncio.run(_count_of(upgraded, E2B_RULE_SET)) == 1
    finally:
        # Back to REVISION, not "head": 0051 (T4.54) lands on top of this one
        # now, and this module's database is staged at REVISION on purpose
        # (see the ``upgraded`` fixture) — ``test_the_models_and_the_migrations_
        # agree`` above is the one that checks the whole chain against "head".
        command.upgrade(config, REVISION)
    assert asyncio.run(_revision_of(upgraded)) == REVISION
    assert asyncio.run(_count_of(upgraded, RATIO10_RULE_SET)) == 1


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
