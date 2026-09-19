"""``0054_meme_gate_crowd_arm`` (T4.66) — its own file and its own database,
``test_migration_0052.py``'s own shape: the two lines this revision owes
``test_migrations.py`` (``HEAD_REVISION`` and ``0022``'s active-set count, 19 →
20) are changed there too, and nothing here depends on them.

What is proved: the seed exists with EXP-M19's four keys (``"0.70"``, 60, 5,
``"0.20"``) on the 15-second clock; it is ``flow_v2/6`` with those **four** keys
added and every other param byte for byte identical; it is paper by
construction (``kind = 'research_only'``, and the executor only ever opens
proposals of an ``operator`` set); the downgrade removes it on a clean database
and refuses while a proposal or a bet references it (§17.7).
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

REVISION = "0054_meme_gate_crowd_arm"
PREVIOUS = "0053_meme_launch_lane_arm"

CROWD_RULE_SET = "01994d00-6c1a-7000-8000-000000000018"
E2B_RULE_SET = "01994d00-6c1a-7000-8000-000000000013"
"""``flow_v2/6`` (``0044``) — this arm's base **and** its control."""

CROWD_KEYS = (
    "min_early_retention_pct",
    "min_early_age_s",
    "min_new_wallets_30s",
    "max_quick_flip_share_30s",
)
"""The keys ``EntryGate`` reads (T4.66) through ``lab_gate_params.gate_from_params``:
two **fractions** as strings, two counts as JSON integers."""
_MINUS_CROWD = " ".join(f"- '{k}'" for k in CROWD_KEYS)

_A_PROPOSAL = (
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at, "
    "  decision, decided_by, decided_at) VALUES (:id, 'GUARD_MINT_54', :rule_set, 'operator', "
    "  'approved', now() + interval '2 minutes', '{}'::jsonb, 'user', now())"
)
_A_BET = (
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, entry_at, entry, "
    "  initial_risk_sol, params) VALUES (:id, :proposal, :rule_set, 'GUARD_MINT_54', 'paper', "
    "  now(), '{}'::jsonb, 0.05, '{}'::jsonb)"
)
_CLEAN: tuple[str, ...] = (
    "DELETE FROM meme_paper_bets WHERE mint = 'GUARD_MINT_54'",
    "DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT_54'",
)


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0054"))


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


def test_the_revision_lands_on_0053_and_fits_the_version_column() -> None:
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
async def test_the_arm_is_seeded_with_the_four_crowd_keys(engine: AsyncEngine) -> None:
    """``flow_v2/10``: ``research_only`` under EXP-M19, active, 15-second clock,
    the four keys with EXP-M19's numbers — the fractions strings, the counts
    numbers — and nothing else of the control moves."""
    async with engine.connect() as connection:
        seeded = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT name || '/' || version || ':' || kind || ':' "
                    "|| coalesce(exp_ref, '-') || ':' || status || ':' || (params ->> 'clock') "
                    "|| ':' || (params ->> 'gate_key') || '/' || (params ->> 'gate_version') "
                    "|| ':' || (params ->> 'min_early_retention_pct') "
                    "|| '/' || jsonb_typeof(params -> 'min_early_retention_pct') "
                    "|| ':' || (params ->> 'min_early_age_s') "
                    "|| '/' || jsonb_typeof(params -> 'min_early_age_s') "
                    "|| ':' || (params ->> 'min_new_wallets_30s') "
                    "|| '/' || jsonb_typeof(params -> 'min_new_wallets_30s') "
                    "|| ':' || (params ->> 'max_quick_flip_share_30s') "
                    "|| '/' || jsonb_typeof(params -> 'max_quick_flip_share_30s') "
                    "|| ':' || (params ->> 'size_sol') || ':' || (params ->> 'min_holders') "
                    "|| ':' || (params ->> 'min_unique_buyers') "
                    "|| ':' || (params ->> 'max_sells_to_buys') "
                    "|| ':' || (params ->> 'pedigree_e2b') "
                    "|| ':' || coalesce(params ->> 'max_recent_drawdown_pct', '-') "
                    "FROM meme_rule_sets WHERE id = :r"
                ),
                {"r": CROWD_RULE_SET},
            )
        ]
    assert seeded == [
        "flow_v2/10:research_only:EXP-M19:active:15s:fluxo_e_holders/3"
        ":0.70/string:60/number:5/number:0.20/string:0.05:20:10:0.6:true:-"
    ], (
        "the pre-registration freezes the four crowd numbers on top of flow_v2/6 "
        "(E2-b, min_holders = 20, 10 buyers, 0,6 sells/buys) — no drawdown guard here"
    )


@pytest.mark.asyncio
async def test_the_arm_is_flow_v2_6_with_exactly_four_keys_added(engine: AsyncEngine) -> None:
    """The whole experiment, as an assertion: drop the four crowd keys from the
    arm and it is the control, byte for byte; the control never had any of
    them. Anything else that moved would make the Δ R of EXP-M19
    unattributable."""
    async with engine.connect() as connection:
        rows = [
            row[0]
            for row in await connection.execute(
                text(
                    f"SELECT ((r.params {_MINUS_CROWD}) = e.params)::text"  # noqa: S608
                    " || ':' || (e.params ?| :keys)::text "
                    "FROM meme_rule_sets r, meme_rule_sets e WHERE r.id = :r AND e.id = :e"
                ),
                {"r": CROWD_RULE_SET, "e": E2B_RULE_SET, "keys": list(CROWD_KEYS)},
            )
        ]
    assert rows == ["true:false"], (
        "flow_v2/10 minus the four crowd keys is flow_v2/6, byte for byte"
    )


@pytest.mark.asyncio
async def test_the_desk_is_untouched_and_the_control_stays_active(engine: AsyncEngine) -> None:
    """``flow_v2/6`` keeps running beside the arm (the comparison is the point)
    and the desk keeps exactly one ``operator`` set: the crowd never decides
    money from this revision."""
    async with engine.connect() as connection:
        control = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT name || '/' || version || ':' || status || ':' "
                    "|| (params ?| :keys)::text FROM meme_rule_sets WHERE id = :e"
                ),
                {"e": E2B_RULE_SET, "keys": list(CROWD_KEYS)},
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
    assert control == ["flow_v2/6:active:false"]
    assert desk == ["operator/5"]


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    """``alembic check`` on a database of its own taken all the way to ``head``
    (the shape ``0050`` settled on, so the assertion survives the next revision
    landing on top): this revision seeds data and changes no schema, so the
    comparison with the models has to stay empty."""
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0054_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


def test_the_downgrade_refuses_while_a_proposal_or_a_bet_references_the_arm(
    upgraded: str,
) -> None:
    """§17.7: a proposal or a bet under ``flow_v2/10`` is evidence of the
    experiment — count, name, stop. ``"-1"`` from ``REVISION`` is this
    revision's own step, whatever lands on top later."""
    config = alembic_config(upgraded)
    proposal = "00000000-0000-4000-8000-000000005401"
    bet = "00000000-0000-4000-8000-000000005402"
    guarded: list[tuple[list[tuple[str, dict[str, object]]], str]] = [
        (
            [(_A_PROPOSAL, {"id": proposal, "rule_set": CROWD_RULE_SET})],
            "proposals reference the seeded flow_v2/10 set",
        ),
        (
            [
                (_A_PROPOSAL, {"id": proposal, "rule_set": E2B_RULE_SET}),
                (
                    _A_BET,
                    {"id": bet, "proposal": proposal, "rule_set": CROWD_RULE_SET},
                ),
            ],
            "bets reference the seeded flow_v2/10 set",
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
        assert asyncio.run(_count_of(upgraded, CROWD_RULE_SET)) == 0, (
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
    assert asyncio.run(_count_of(upgraded, CROWD_RULE_SET)) == 1


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
