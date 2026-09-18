"""``0052_meme_gate_after_drop_arm`` (T4.61a) — its own file and its own database.

A new file, in ``test_migration_0050.py``'s shape, because ``test_migrations.py``
is being edited by other tasks while this revision is written; the two lines this
revision owes that file (``HEAD_REVISION`` and ``0022``'s active-set count, 17 →
18) are changed there too, and nothing here depends on them.

What is proved: the seed exists with ``max_recent_drawdown_pct = "0.50"`` under
EXP-M13 on the 15-second clock; it is ``flow_v2/6`` with that **one** key added
and every other param byte for byte identical; it is paper by construction
(``kind = 'research_only'``, and the executor only ever opens proposals of an
``operator`` set); the downgrade removes it on a clean database and refuses
while a proposal or a bet references it (§17.7).
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

REVISION = "0052_meme_gate_after_drop_arm"
PREVIOUS = "0051_meme_treasury_swaps"

AFTER_DROP_RULE_SET = "01994d00-6c1a-7000-8000-000000000016"
E2B_RULE_SET = "01994d00-6c1a-7000-8000-000000000013"
"""``flow_v2/6`` (``0044``) — this arm's base **and** its control."""

DRAWDOWN_KEY = "max_recent_drawdown_pct"
"""The key ``EntryGate`` reads (T4.52b-2) through ``lab_models._gate_from_params``:
a **fraction** as a string. The window (60 s) and the gap (30 s) are the gate's
defaults and are not seeded — the page froze them with the arm."""

_A_PROPOSAL = (
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at, "
    "  decision, decided_by, decided_at) VALUES (:id, 'GUARD_MINT_52', :rule_set, 'operator', "
    "  'approved', now() + interval '2 minutes', '{}'::jsonb, 'user', now())"
)
_A_BET = (
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, entry_at, entry, "
    "  initial_risk_sol, params) VALUES (:id, :proposal, :rule_set, 'GUARD_MINT_52', 'paper', "
    "  now(), '{}'::jsonb, 0.05, '{}'::jsonb)"
)
_CLEAN: tuple[str, ...] = (
    "DELETE FROM meme_paper_bets WHERE mint = 'GUARD_MINT_52'",
    "DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT_52'",
)


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0052"))


@pytest.fixture(scope="module")
def upgraded(db_url: str) -> Iterator[str]:
    """This revision by name, not ``head``: today they coincide, and the day
    another lands on top this module's downgrade assertions (``"-1"`` ->
    ``PREVIOUS``) keep being about the one step this revision itself takes."""
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


def test_the_revision_lands_on_0051_and_fits_the_version_column() -> None:
    """Pure: no database, no container — the chain this task was told to extend,
    and the 32-character ceiling of ``alembic_version.version_num`` (§30.7) the
    brief's own slug would have broken. Read as text, like ``0050``'s twin."""
    source = (REPO_ROOT / "infra" / "migrations" / "versions" / f"{REVISION}.py").read_text(
        encoding="utf-8"
    )
    assert f'revision: str = "{REVISION}"' in source
    assert f'down_revision: str | None = "{PREVIOUS}"' in source
    assert len(REVISION) <= 32


def test_only_an_operator_set_reaches_the_executor_so_a_research_arm_is_paper() -> None:
    """Why ``kind = 'research_only'`` *is* the paper flag, read from the executor
    rather than assumed: ``auto_approve`` selects proposals of an **operator**
    set, so no ``research_only`` arm can ever be opened on money."""
    source = (
        REPO_ROOT / "services" / "meme-executor" / "hunter_meme_executor" / "auto_approve.py"
    ).read_text(encoding="utf-8")
    assert "\"WHERE rs.kind = 'operator' AND rs.status = 'active' \"" in source


@pytest.mark.asyncio
async def test_the_arm_is_seeded_with_the_drawdown_ceiling_of_a_half(engine: AsyncEngine) -> None:
    """``flow_v2/9``: ``research_only`` under EXP-M13, active, 15-second clock,
    ``max_recent_drawdown_pct = "0.50"`` — KB-0118's X. The value is a string,
    like every decimal in these params, and nothing else of the control moves."""
    async with engine.connect() as connection:
        seeded = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT name || '/' || version || ':' || kind || ':' "  # noqa: S608
                    "|| coalesce(exp_ref, '-') || ':' || status || ':' "
                    f"|| (params ->> '{DRAWDOWN_KEY}') || ':' || (params ->> 'clock') "
                    "|| ':' || (params ->> 'gate_key') || '/' || (params ->> 'gate_version') "
                    "|| ':' || (params ->> 'size_sol') || ':' || (params ->> 'target_x') "
                    "|| ':' || (params ->> 'max_participation_pct') "
                    "|| ':' || (params ->> 'min_holders') "
                    "|| ':' || (params ->> 'min_unique_buyers') "
                    "|| ':' || (params ->> 'max_sells_to_buys') "
                    f"|| ':' || jsonb_typeof(params -> '{DRAWDOWN_KEY}') "
                    "|| ':' || coalesce(params ->> 'recent_drawdown_window_s', '-') "
                    "FROM meme_rule_sets WHERE id = :r"
                ),
                {"r": AFTER_DROP_RULE_SET},
            )
        ]
    assert seeded == [
        "flow_v2/9:research_only:EXP-M13:active:0.50:15s:fluxo_e_holders/3"
        ":0.05:3:1:20:10:0.6:string:-"
    ], (
        "the pre-registration freezes the exits, the size, the 1 % participation cap, "
        "min_holders = 20, the floor of 10 buyers and the 0,6 sells/buys ceiling as the "
        "control's — only the drawdown guard is switched on, with the gate's default window"
    )


@pytest.mark.asyncio
async def test_the_arm_is_flow_v2_6_with_exactly_one_key_added(engine: AsyncEngine) -> None:
    """The whole experiment, as an assertion: drop ``max_recent_drawdown_pct``
    from the arm and it is the control, byte for byte; the control never had
    the key. Anything else that moved would make the Δ R of EXP-M13
    unattributable."""
    async with engine.connect() as connection:
        rows = [
            row[0]
            for row in await connection.execute(
                text(
                    f"SELECT ((r.params - '{DRAWDOWN_KEY}') = e.params)::text"  # noqa: S608
                    f" || ':' || (r.params ->> '{DRAWDOWN_KEY}') "
                    f"|| ':' || (e.params ? '{DRAWDOWN_KEY}')::text "
                    "FROM meme_rule_sets r, meme_rule_sets e WHERE r.id = :r AND e.id = :e"
                ),
                {"r": AFTER_DROP_RULE_SET, "e": E2B_RULE_SET},
            )
        ]
    assert rows == ["true:0.50:false"], "flow_v2/9 minus the guard is flow_v2/6, byte for byte"


@pytest.mark.asyncio
async def test_the_desk_is_untouched_and_the_control_stays_active(engine: AsyncEngine) -> None:
    """``flow_v2/6`` keeps running beside the arm (the comparison is the point)
    and the desk keeps exactly one ``operator`` set: the guard never fires on
    money from this revision."""
    async with engine.connect() as connection:
        control = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT name || '/' || version || ':' || status || ':' "  # noqa: S608
                    f"|| coalesce(params ->> '{DRAWDOWN_KEY}', '-') FROM meme_rule_sets "
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
    assert control == ["flow_v2/6:active:-"]
    assert desk == ["operator/5"]


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    """``alembic check`` on a database of its own taken all the way to ``head``
    (the shape ``0050`` settled on, so the assertion survives the next revision
    landing on top): this revision seeds data and changes no schema, so the
    comparison with the models has to stay empty."""
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0052_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


def test_the_downgrade_refuses_while_a_proposal_or_a_bet_references_the_arm(
    upgraded: str,
) -> None:
    """§17.7: a proposal or a bet under ``flow_v2/9`` is evidence of the
    experiment — count, name, stop. ``"-1"`` from ``REVISION`` is this
    revision's own step, whatever lands on top later."""
    config = alembic_config(upgraded)
    proposal = "00000000-0000-4000-8000-000000005201"
    bet = "00000000-0000-4000-8000-000000005202"
    guarded: list[tuple[list[tuple[str, dict[str, object]]], str]] = [
        (
            [(_A_PROPOSAL, {"id": proposal, "rule_set": AFTER_DROP_RULE_SET})],
            "proposals reference the seeded flow_v2/9 set",
        ),
        (
            [
                (_A_PROPOSAL, {"id": proposal, "rule_set": E2B_RULE_SET}),
                (
                    _A_BET,
                    {"id": bet, "proposal": proposal, "rule_set": AFTER_DROP_RULE_SET},
                ),
            ],
            "bets reference the seeded flow_v2/9 set",
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
        assert asyncio.run(_count_of(upgraded, AFTER_DROP_RULE_SET)) == 0, (
            "the seed is the whole revision: reversing it leaves no row behind"
        )
        assert asyncio.run(_count_of(upgraded, E2B_RULE_SET)) == 1
    finally:
        # Back to REVISION, not "head": this module's database is staged at
        # REVISION on purpose (see the ``upgraded`` fixture) — ``test_the_
        # models_and_the_migrations_agree`` above is the one that checks the
        # whole chain against "head".
        command.upgrade(config, REVISION)
    assert asyncio.run(_revision_of(upgraded)) == REVISION
    assert asyncio.run(_count_of(upgraded, AFTER_DROP_RULE_SET)) == 1


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
