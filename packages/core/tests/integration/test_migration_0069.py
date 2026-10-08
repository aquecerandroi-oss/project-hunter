"""``0069_meme_absorb_semdump_arm`` (H-031b, EXP-M27) — its own file and its own
database, ``test_migration_0065.py``'s shape. ``test_migrations.py`` carries
the active-set count (+1 = 27 here, 30 once the held ``0070_meme_mature_chart_arms``
sits on top); nothing here depends on it, and every upgrade here is by name,
never ``head``.

What is proved: the twin exists (``research_only`` under EXP-M27, active, on
``absorb_v0/2``'s ``15s`` clock, ``absorb_v0/2``'s ``code_ref``); its document
is ``absorb_v0/2``'s **plus** ``"exit_on_creator_dump": false`` and nothing else,
key by key; the params load the way the worker loads them — the same gate, the
same ticket and ceilings, the same exits **except** ``creator_dump``, and the
bet records ``false`` (a worker that ignores the key fails here); **the
executor's own selection query never returns a proposal of the twin** (run, not
grepped); the desk and ``absorb_v0/2`` are untouched; the downgrade removes
the seed on a clean database and refuses, by name, while any row of the five
tables with a foreign key to ``meme_rule_sets`` references it. The
upgrade's refusals (and the row lock against a racing ``--set-param``) are
``test_migration_0069_guards.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from hunter_meme_executor.auto_approve import operator_proposals
from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.lab_params import effective_params
from hunter_meme_worker.lab_repo import load_active_rule_sets
from hunter_meme_worker.lab_repo_pedigree import ABSORB_SEMDUMP_RULE_SET_ID

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database

pytestmark = pytest.mark.integration

REVISION = "0069_meme_absorb_semdump_arm"
PREVIOUS = "0068_meme_wallet_exceptions"

TWIN = "01994d00-6c1a-7000-8000-000000000022"
ORIGINAL = "01994d00-6c1a-7000-8000-00000000001b"
OPERATOR_6 = "01994d00-6c1a-7000-8000-000000000019"

_PROPOSED = (
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, expires_at, "
    "  features_end_time) VALUES (:id, 'GUARD_MINT_69', :rule_set, 'rules', 'proposed', "
    "  CAST(:at AS timestamptz), CAST(:at AS timestamptz) + interval '3 minutes', "
    "  CAST(:at AS timestamptz))"
)
_APPROVED = (
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at, "
    "  decision, decided_by, decided_at) VALUES (:id, 'GUARD_MINT_69', :rule_set, 'operator', "
    "  'approved', now() + interval '2 minutes', '{}'::jsonb, 'user', now())"
)
_A_BET = (
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, entry_at, entry, "
    "  initial_risk_sol, params) VALUES (:id, :proposal, :rule_set, 'GUARD_MINT_69', 'paper', "
    "  now(), '{}'::jsonb, 0.07, '{}'::jsonb)"
)
_A_REFUSAL = (
    "INSERT INTO meme_gate_refusals_by_mint (as_of, rule_set_id, mint, refusal) "
    "VALUES (now(), :rule_set, 'GUARD_MINT_69', 'flow_not_positive')"
)
_A_PARAM_CHANGE = (
    "INSERT INTO meme_rule_set_param_history (id, rule_set_id, key, old_value, new_value, "
    "  changed_by, reason) VALUES (:id, :rule_set, 'max_hold_s', '300'::jsonb, '301'::jsonb, "
    "  'test', 'H-031b guard')"
)
_AN_OPPORTUNITY = (
    "INSERT INTO meme_mature_opportunities (id, rule_set_id, mint, evaluated_at, "
    "  features_end_time, features_version, code_ref, inputs, gate, coverage_version, "
    "  coverage_status, coverage, proposal_refusals, no_proposal_reason, lane_since) "
    "VALUES ('00000000-0000-4000-8000-000000006914', :rule_set, 'GUARD_MINT_69', now(), now(), "
    "  'meme_features_v3', 't', '{}', '[]', 'v1', 'unread', '{}', '{creator_serial}', "
    "  'refused', now())"
)
_CLEAN: tuple[str, ...] = (
    "DELETE FROM meme_mature_opportunities WHERE mint = 'GUARD_MINT_69'",
    "DELETE FROM meme_gate_refusals_by_mint WHERE mint = 'GUARD_MINT_69'",
    "DELETE FROM meme_paper_bets WHERE mint = 'GUARD_MINT_69'",
    "DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT_69'",
    "DELETE FROM meme_rule_set_param_history WHERE reason = 'H-031b guard'",
)


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0069"))


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
        await created.dispose()


async def _write(url: str, statements: list[tuple[str, dict[str, object]]]) -> None:
    created = async_engine(url)
    try:
        async with created.begin() as connection:
            for statement, parameters in statements:
                await connection.execute(text(statement), parameters)
    finally:
        await created.dispose()


async def _scalar(url: str, sql: str, **params: object) -> Any:
    created = async_engine(url)
    try:
        async with created.connect() as connection:
            return await connection.scalar(text(sql), params)
    finally:
        await created.dispose()


def _revision_of(url: str) -> str | None:
    return asyncio.run(_scalar(url, "SELECT version_num FROM alembic_version"))


def _count_of(url: str, rule_set: str) -> int:
    return int(
        asyncio.run(_scalar(url, "SELECT count(*) FROM meme_rule_sets WHERE id = :r", r=rule_set))
    )


def test_the_revision_lands_on_0068_and_fits_the_version_column() -> None:
    source = (REPO_ROOT / "infra" / "migrations" / "versions" / f"{REVISION}.py").read_text(
        encoding="utf-8"
    )
    assert f'revision: str = "{REVISION}"' in source
    assert f'down_revision: str | None = "{PREVIOUS}"' in source
    assert len(REVISION) <= 32
    assert ABSORB_SEMDUMP_RULE_SET_ID == TWIN, "the id the desk's pedigree subtracts is 0069's own"


@pytest.mark.asyncio
async def test_the_twin_is_the_original_plus_the_switch_and_nothing_else(
    engine: AsyncEngine,
) -> None:
    params = "SELECT params FROM meme_rule_sets WHERE id = :r"
    async with engine.connect() as connection:
        twin = await connection.scalar(text(params), {"r": TWIN})
        original = await connection.scalar(text(params), {"r": ORIGINAL})
        seeded = await connection.scalar(
            text(
                "SELECT t.name || '/' || t.version || ':' || t.kind || ':' || t.exp_ref || ':' "
                "|| t.status || ':' || (t.params ->> 'clock') || ':' "
                "|| (t.code_ref = a.code_ref)::text "
                "FROM meme_rule_sets t, meme_rule_sets a WHERE t.id = :t AND a.id = :a"
            ),
            {"t": TWIN, "a": ORIGINAL},
        )
    assert seeded == "absorb_semdump_v0/1:research_only:EXP-M27:active:15s:true"
    assert twin["exit_on_creator_dump"] is False
    assert "exit_on_creator_dump" not in original, "0058's original never named the switch"
    assert {k: v for k, v in twin.items() if k != "exit_on_creator_dump"} == original


async def _spec(engine: AsyncEngine, rule_set: str) -> RuleSetSpec:
    async with engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT id::text, name, version, kind, exp_ref, status, code_ref, params "
                        "FROM meme_rule_sets WHERE id = :r"
                    ),
                    {"r": rule_set},
                )
            )
            .mappings()
            .one()
        )
    return RuleSetSpec.from_params(**dict(row))


@pytest.mark.asyncio
async def test_the_params_load_the_way_the_worker_loads_them(engine: AsyncEngine) -> None:
    twin, original = await _spec(engine, TWIN), await _spec(engine, ORIGINAL)
    assert (twin.kind, twin.clock, twin.exp_ref) == ("research_only", "15s", "EXP-M27")
    assert (twin.require_absorb_sell_seen, twin.require_absorb_confirmed) == (True, False)
    assert replace(twin.gate, description=original.gate.description) == original.gate
    ceilings = (
        "size_sol", "max_sol_per_bet", "max_exposure_per_mint_sol", "max_open_positions",
        "wallet_max_sol", "daily_loss_cap_sol", "fee_pct", "priority_fee_sol", "ttl_s",
    )  # fmt: skip
    assert [getattr(twin, k) for k in ceilings] == [getattr(original, k) for k in ceilings]
    assert (twin.exit_on_creator_dump, original.exit_on_creator_dump) == (False, True)
    mine, theirs = effective_params(twin, {}), effective_params(original, {})
    assert not isinstance(mine, str) and not isinstance(theirs, str)
    assert mine.exit_rules() == replace(theirs.exit_rules(), exit_on_creator_dump=False), (
        "the same exits, minus the creator's dump"
    )
    assert mine.as_json()["exit_on_creator_dump"] is False, "every twin bet says so"
    assert theirs.as_json()["exit_on_creator_dump"] is True
    async with AsyncSession(engine) as session:
        labels = {s.label for s in await load_active_rule_sets(session)}
    assert {"absorb_semdump_v0/1", "absorb_v0/2", "absorb_v0/1", "operator/5"} <= labels


@pytest.mark.asyncio
async def test_the_executors_own_query_never_selects_the_twin(upgraded: str) -> None:
    """Paper by construction: ``auto_approve.operator_proposals`` — the live
    executor's selection — run on a ``proposed`` paper proposal of each set."""
    now = datetime.now(UTC)
    operator_5 = "01994d00-6c1a-7000-8000-000000000011"
    ids = {
        "twin": "00000000-0000-4000-8000-000000006901",
        "desk": "00000000-0000-4000-8000-000000006902",
    }
    await _write(
        upgraded,
        [
            (_PROPOSED, {"id": ids["twin"], "rule_set": TWIN, "at": now}),
            (_PROPOSED, {"id": ids["desk"], "rule_set": operator_5, "at": now}),
        ],
    )
    created = async_engine(upgraded)
    try:
        async with AsyncSession(created) as session:
            selected = {
                p.id for p in await operator_proposals(session, now=now + timedelta(seconds=1))
            }
    finally:
        await created.dispose()
        await _write(upgraded, [(statement, {}) for statement in _CLEAN])
    assert ids["desk"] in selected, "the query is live: the desk's own proposal is selected"
    assert ids["twin"] not in selected


@pytest.mark.asyncio
async def test_the_desk_and_the_original_are_untouched(engine: AsyncEngine) -> None:
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
        switched = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT name || '/' || version FROM meme_rule_sets "
                    "WHERE params ? 'exit_on_creator_dump'"
                )
            )
        ]
    assert desk == ["operator/5", "operator/6"]
    assert switched == ["absorb_semdump_v0/1"], "no other set names the switch"


def test_the_downgrade_refuses_while_any_row_references_the_twin(upgraded: str) -> None:
    config = alembic_config(upgraded)
    proposal = "00000000-0000-4000-8000-000000006911"
    bet = "00000000-0000-4000-8000-000000006912"
    change = "00000000-0000-4000-8000-000000006913"
    guarded: list[tuple[list[tuple[str, dict[str, object]]], str]] = [
        (
            [(_APPROVED, {"id": proposal, "rule_set": TWIN})],
            "proposals reference the seeded absorb_semdump_v0 set - they are H-031b's "
            "pairs and cannot be removed under them",
        ),
        (
            [
                (_APPROVED, {"id": proposal, "rule_set": OPERATOR_6}),
                (_A_BET, {"id": bet, "proposal": proposal, "rule_set": TWIN}),
            ],
            "bets reference the seeded absorb_semdump_v0 set",
        ),
        (
            [(_A_PARAM_CHANGE, {"id": change, "rule_set": TWIN})],
            "param history rows reference the seeded absorb_semdump_v0 set",
        ),
        (
            [(_A_REFUSAL, {"rule_set": TWIN})],
            "refusal rows reference the seeded absorb_semdump_v0 set",
        ),
        (
            [(_AN_OPPORTUNITY, {"rule_set": TWIN})],
            "opportunity records reference the seeded absorb_semdump_v0 set",
        ),
    ]
    for statements, message in guarded:
        asyncio.run(_write(upgraded, statements))
        try:
            with pytest.raises(DBAPIError, match=message):
                command.downgrade(config, "-1")
            assert _revision_of(upgraded) == REVISION, "the downgrade must not commit"
        finally:
            asyncio.run(_write(upgraded, [(statement, {}) for statement in _CLEAN]))


def test_the_downgrade_removes_the_seed_on_a_clean_database_and_comes_back(
    upgraded: str,
) -> None:
    config = alembic_config(upgraded)
    command.downgrade(config, "-1")
    try:
        assert _revision_of(upgraded) == PREVIOUS
        assert _count_of(upgraded, TWIN) == 0 and _count_of(upgraded, ORIGINAL) == 1
    finally:
        command.upgrade(config, REVISION)
    assert _revision_of(upgraded) == REVISION and _count_of(upgraded, TWIN) == 1
