"""``0053_meme_launch_lane_arm`` (T4.67a) — its own file and its own database,
``test_migration_0052.py``'s own shape: the two lines this revision owes
``test_migrations.py`` (``HEAD_REVISION`` and ``0022``'s active-set count, 18 →
19) are changed there too, and nothing here depends on them.

What is proved: the seed exists with every EXP-M18 number, ``clock =
"event"`` (so the 15-second/minute engines never judge it —
``lab_models.CLOCKS`` never lists that value), it is paper by construction
(``kind = 'research_only'``, and the executor only ever opens proposals of an
``operator`` set); ``meme_paper_bets.mark_source``'s CHECK now accepts
``solana_ws`` beside ``curve``/``pool_tape``; the downgrade removes the seed
on a clean database (never narrowing the CHECK back) and refuses while a
proposal or a bet references it (§17.7).
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

REVISION = "0053_meme_launch_lane_arm"
PREVIOUS = "0052_meme_gate_after_drop_arm"

LAUNCH_V0_RULE_SET = "01994d00-6c1a-7000-8000-000000000017"

_A_PROPOSAL = (
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at, "
    "  decision, decided_by, decided_at) VALUES (:id, 'GUARD_MINT_53', :rule_set, 'operator', "
    "  'approved', now() + interval '2 minutes', '{}'::jsonb, 'user', now())"
)
_A_BET = (
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, entry_at, entry, "
    "  initial_risk_sol, params) VALUES (:id, :proposal, :rule_set, 'GUARD_MINT_53', 'paper', "
    "  now(), '{}'::jsonb, 0.01, '{}'::jsonb)"
)
_CLEAN: tuple[str, ...] = (
    "DELETE FROM meme_paper_bets WHERE mint = 'GUARD_MINT_53'",
    "DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT_53'",
)


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0053"))


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


async def _write(url: str, statements: list[tuple[str, dict[str, object]]]) -> None:
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


def test_the_revision_lands_on_0052_and_fits_the_version_column() -> None:
    """Pure: no database, no container — the chain this task was told to
    extend, and the 32-character ceiling of ``alembic_version.version_num``."""
    source = (REPO_ROOT / "infra" / "migrations" / "versions" / f"{REVISION}.py").read_text(
        encoding="utf-8"
    )
    assert f'revision: str = "{REVISION}"' in source
    assert f'down_revision: str | None = "{PREVIOUS}"' in source
    assert len(REVISION) <= 32


def test_only_an_operator_set_reaches_the_executor_so_the_arm_is_paper() -> None:
    source = (
        REPO_ROOT / "services" / "meme-executor" / "hunter_meme_executor" / "auto_approve.py"
    ).read_text(encoding="utf-8")
    assert "\"WHERE rs.kind = 'operator' AND rs.status = 'active' \"" in source


@pytest.mark.asyncio
async def test_the_arm_is_seeded_with_every_exp_m18_number(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        seeded = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT name || '/' || version || ':' || kind || ':' "
                    "|| coalesce(exp_ref, '-') || ':' || status "
                    "|| ':' || (params ->> 'clock') "
                    "|| ':' || (params ->> 'size_sol') "
                    "|| ':' || (params ->> 'max_creator_initial_sol') "
                    "|| ':' || (params ->> 'exit_key') "
                    "|| ':' || (params ->> 'time_stop_s') "
                    "|| ':' || (params ->> 'exit_on_first_third_party_sell') "
                    "|| ':' || (params ->> 'max_drawdown_from_peak_pct') "
                    "FROM meme_rule_sets WHERE id = :r"
                ),
                {"r": LAUNCH_V0_RULE_SET},
            )
        ]
    assert seeded == [
        "launch_v0/1:research_only:EXP-M18:active:event:0.01:2:"
        "lancamento_6s_ou_primeiro_sell:6:true:20"
    ]


@pytest.mark.asyncio
async def test_the_desk_is_untouched_and_the_operator_set_stays_alone(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as connection:
        desk = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT name || '/' || version FROM meme_rule_sets "
                    "WHERE kind = 'operator' AND status = 'active' ORDER BY version"
                )
            )
        ]
    assert desk == ["operator/5"]


def test_mark_source_check_widens_to_accept_solana_ws(upgraded: str) -> None:
    """The one schema change: ``solana_ws`` is now a known label, an
    arbitrary string still is not."""
    other_rule_set = "01994d00-6c1a-7000-8000-000000000013"  # flow_v2/6 — any other set
    bad_proposal, bad_bet = (
        "00000000-0000-4000-8000-000000005303",
        "00000000-0000-4000-8000-000000005304",
    )
    good_proposal, good_bet = (
        "00000000-0000-4000-8000-000000005305",
        "00000000-0000-4000-8000-000000005306",
    )
    a_proposal = (
        "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at, "
        "  decision, decided_by, decided_at) VALUES (:id, 'GUARD_MINT_53_MARK', :rule_set, "
        "  'operator', 'approved', now() + interval '2 minutes', '{}'::jsonb, 'user', now())"
    )
    a_bet_with_source = (
        "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, entry_at, entry, "
        "  initial_risk_sol, params, mark_source, mark_sol, mark_at) "
        "VALUES (:id, :proposal, :rule_set, 'GUARD_MINT_53_MARK', 'paper', now(), '{}'::jsonb, "
        "  0.01, '{}'::jsonb, :source, 0.01, now())"
    )
    try:
        asyncio.run(
            _write(upgraded, [(a_proposal, {"id": bad_proposal, "rule_set": other_rule_set})])
        )
        with pytest.raises(DBAPIError, match="mark_source_is_a_known_label"):
            asyncio.run(
                _write(
                    upgraded,
                    [
                        (
                            a_bet_with_source,
                            {
                                "id": bad_bet,
                                "proposal": bad_proposal,
                                "rule_set": other_rule_set,
                                "source": "not_a_known_source",
                            },
                        )
                    ],
                )
            )
        asyncio.run(
            _write(
                upgraded,
                [
                    (a_proposal, {"id": good_proposal, "rule_set": other_rule_set}),
                    (
                        a_bet_with_source,
                        {
                            "id": good_bet,
                            "proposal": good_proposal,
                            "rule_set": other_rule_set,
                            "source": "solana_ws",
                        },
                    ),
                ],
            )
        )
    finally:
        asyncio.run(
            _write(
                upgraded,
                [
                    ("DELETE FROM meme_paper_bets WHERE mint = 'GUARD_MINT_53_MARK'", {}),
                    ("DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT_53_MARK'", {}),
                ],
            )
        )


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0053_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


def test_the_downgrade_refuses_while_a_proposal_or_a_bet_references_the_arm(
    upgraded: str,
) -> None:
    config = alembic_config(upgraded)
    proposal = "00000000-0000-4000-8000-000000005301"
    bet = "00000000-0000-4000-8000-000000005302"
    other_rule_set = "01994d00-6c1a-7000-8000-000000000013"  # flow_v2/6 — any other set
    guarded: list[tuple[list[tuple[str, dict[str, object]]], str]] = [
        (
            [(_A_PROPOSAL, {"id": proposal, "rule_set": LAUNCH_V0_RULE_SET})],
            "proposals reference the seeded launch_v0/1 set",
        ),
        (
            [
                (_A_PROPOSAL, {"id": proposal, "rule_set": other_rule_set}),
                (_A_BET, {"id": bet, "proposal": proposal, "rule_set": LAUNCH_V0_RULE_SET}),
            ],
            "bets reference the seeded launch_v0/1 set",
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
    config = alembic_config(upgraded)
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_revision_of(upgraded)) == PREVIOUS
        assert asyncio.run(_count_of(upgraded, LAUNCH_V0_RULE_SET)) == 0
    finally:
        command.upgrade(config, REVISION)
    assert asyncio.run(_revision_of(upgraded)) == REVISION
    assert asyncio.run(_count_of(upgraded, LAUNCH_V0_RULE_SET)) == 1


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
