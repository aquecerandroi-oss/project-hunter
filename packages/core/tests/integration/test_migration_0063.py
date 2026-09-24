"""``0063_meme_pullback_entry_arm`` (T4.91, EXP-M24) — its own file and its own
database, ``test_migration_0060.py``'s own shape: the two lines this revision
owes ``test_migrations.py`` (``HEAD_REVISION`` and the active-set count,
24 → 25) are changed there too, and nothing here depends on them.

What is proved: the arm exists (``research_only`` under EXP-M24, active, on
``operator/5``'s ``15s`` clock so the event lane reads it) and carries the
pullback cell 3 % / 60 s (H-017); the exit and the size are the brief's (1,15× /
trailing 10 % armed at the entry / 300 s / 0,07 SOL), with paper ceilings;
subtracting the thirteen keys it owns leaves ``operator/5`` byte for byte;
every decimal is a string; the params load the way the worker loads them;
**the executor's own selection query never returns a proposal of this arm**
(run against the database, not grepped); the desk is untouched; the upgrade
refuses without an active ``operator/5``; and the downgrade removes the seed
on a clean database and refuses while a proposal or a bet references it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from hunter_meme_executor.auto_approve import operator_proposals
from hunter_meme_worker.entry_pullback import EntryPullback
from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.lab_params import effective_params
from hunter_meme_worker.lab_repo import load_active_rule_sets

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database

pytestmark = pytest.mark.integration

REVISION = "0063_meme_pullback_entry_arm"
PREVIOUS = "0062_meme_decision_tapes"

ARM = "01994d00-6c1a-7000-8000-00000000001d"
OPERATOR_5 = "01994d00-6c1a-7000-8000-000000000011"
OPERATOR_6 = "01994d00-6c1a-7000-8000-000000000019"

ARM_KEYS: tuple[str, ...] = (
    "exit_key",
    "target_x",
    "trailing_pct",
    "trailing_arm_x",
    "max_hold_s",
    "size_sol",
    "max_sol_per_bet",
    "max_exposure_per_mint_sol",
    "max_open_positions",
    "daily_loss_cap_sol",
    "wallet_max_sol",
    "entry_pullback_pct",
    "entry_pullback_window_s",
)
"""``ddl/meme_pullback_entry_arm.PULLBACK_ARM_KEYS``, frozen here too."""

_PROPOSED = (
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, expires_at, "
    "  features_end_time) VALUES (:id, 'GUARD_MINT_63', :rule_set, 'rules', 'proposed', "
    "  CAST(:at AS timestamptz), CAST(:at AS timestamptz) + interval '3 minutes', "
    "  CAST(:at AS timestamptz))"
)
_APPROVED = (
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at, "
    "  decision, decided_by, decided_at) VALUES (:id, 'GUARD_MINT_63', :rule_set, 'operator', "
    "  'approved', now() + interval '2 minutes', '{}'::jsonb, 'user', now())"
)
_A_BET = (
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, entry_at, entry, "
    "  initial_risk_sol, params) VALUES (:id, :proposal, :rule_set, 'GUARD_MINT_63', 'paper', "
    "  now(), '{}'::jsonb, 0.07, '{}'::jsonb)"
)
_A_REFUSAL = (
    "INSERT INTO meme_gate_refusals_by_mint (as_of, rule_set_id, mint, refusal) "
    "VALUES (now(), :rule_set, 'GUARD_MINT_63', 'no_pullback')"
)
_CLEAN: tuple[str, ...] = (
    "DELETE FROM meme_gate_refusals_by_mint WHERE mint = 'GUARD_MINT_63'",
    "DELETE FROM meme_paper_bets WHERE mint = 'GUARD_MINT_63'",
    "DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT_63'",
)


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0063"))


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


def test_the_revision_lands_on_0062_and_fits_the_version_column() -> None:
    source = (REPO_ROOT / "infra" / "migrations" / "versions" / f"{REVISION}.py").read_text(
        encoding="utf-8"
    )
    assert f'revision: str = "{REVISION}"' in source
    assert f'down_revision: str | None = "{PREVIOUS}"' in source
    assert len(REVISION) <= 32


@pytest.mark.asyncio
async def test_the_arm_carries_the_cell_the_desks_exit_and_paper_ceilings(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as connection:
        seeded = await connection.scalar(
            text(
                "SELECT name || '/' || version || ':' || kind || ':' || exp_ref || ':' || status "
                "|| ':' || (params ->> 'clock') || ':' || (params ->> 'gate_key') "
                "|| ':' || (params ->> 'entry_pullback_pct') "
                "|| '/' || jsonb_typeof(params -> 'entry_pullback_pct') "
                "|| ':' || (params ->> 'entry_pullback_window_s') "
                "|| '/' || jsonb_typeof(params -> 'entry_pullback_window_s') "
                "|| ':' || (params ->> 'exit_key') || ':' || (params ->> 'target_x') "
                "|| ':' || (params ->> 'trailing_pct') "
                "|| ':' || coalesce(params ->> 'trailing_arm_x', 'null') "
                "|| ':' || (params ->> 'max_hold_s') || ':' || (params ->> 'size_sol') "
                "|| ':' || (params ->> 'max_sol_per_bet') "
                "|| ':' || (params ->> 'max_exposure_per_mint_sol') "
                "|| ':' || (params ->> 'max_open_positions') "
                "|| ':' || (params ->> 'daily_loss_cap_sol') || ':' || (params ->> 'wallet_max_sol') "
                "FROM meme_rule_sets WHERE id = :r"
            ),
            {"r": ARM},
        )
    assert seeded == (
        "recuo_v1/1:research_only:EXP-M24:active:15s:fluxo_e_holders:3/string:60/number"
        ":alvo_1_15x_trailing_10_tempo_5m:1.15:10:null:300:0.07:0.07:0.07:25:10.0:100.0"
    )


@pytest.mark.asyncio
async def test_minus_the_keys_it_owns_the_arm_is_operator_5(engine: AsyncEngine) -> None:
    """The pairing EXP-M24 needs, as one assertion: the same gate document."""
    async with engine.connect() as connection:
        same = await connection.scalar(
            text(
                "SELECT (a.params - CAST(:keys AS text[]) = d.params - CAST(:keys AS text[]))::text "
                "FROM meme_rule_sets a, meme_rule_sets d WHERE a.id = :a AND d.id = :d"
            ),
            {"keys": list(ARM_KEYS), "a": ARM, "d": OPERATOR_5},
        )
        floats = await connection.scalar(
            text(
                "SELECT count(*) FROM meme_rule_sets, jsonb_each(params) "
                "WHERE id = :a AND jsonb_typeof(value) = 'number' AND value::text LIKE '%.%'"
            ),
            {"a": ARM},
        )
    assert same == "true"
    assert floats == 0, "every SOL/percent/multiple is a string; only counts are numbers"


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
    spec = await _spec(engine, ARM)
    assert (spec.kind, spec.clock, spec.exp_ref) == ("research_only", "15s", "EXP-M24")
    assert spec.entry_pullback == EntryPullback(pct=Decimal(3), window_s=60)
    assert (spec.size_sol, spec.max_sol_per_bet, spec.max_exposure_per_mint_sol) == (
        Decimal("0.07"),
    ) * 3
    assert (spec.max_open_positions, spec.wallet_max_sol, spec.daily_loss_cap_sol) == (
        25,
        Decimal("100.0"),
        Decimal("10.0"),
    )
    effective = effective_params(spec, {})
    assert not isinstance(effective, str), effective
    rules = effective.exit_rules()
    assert (rules.target_multiple, rules.trailing_drawdown_pct) == (Decimal("1.15"), Decimal(10))
    assert rules.trailing_arm_multiple is None and rules.time_stop_s == 300
    desk = await _spec(engine, OPERATOR_5)
    same_gate = replace(spec.gate, description=desk.gate.description)
    assert same_gate == desk.gate, "the entry gate is operator/5's, criterion by criterion"
    assert desk.entry_pullback is None, "the desk itself never waits"
    async with AsyncSession(engine) as session:
        labels = {s.label for s in await load_active_rule_sets(session)}
    assert {"recuo_v1/1", "operator/5", "operator/6"} <= labels


@pytest.mark.asyncio
async def test_the_executors_own_query_never_selects_the_arm(upgraded: str) -> None:
    """Paper by construction: ``auto_approve.operator_proposals`` — the live
    executor's selection — run on a ``proposed`` paper proposal of each set."""
    now = datetime.now(UTC)
    ids = {
        "arm": "00000000-0000-4000-8000-000000006301",
        "desk": "00000000-0000-4000-8000-000000006302",
    }
    await _write(
        upgraded,
        [
            (_PROPOSED, {"id": ids["arm"], "rule_set": ARM, "at": now}),
            (_PROPOSED, {"id": ids["desk"], "rule_set": OPERATOR_5, "at": now}),
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
    assert ids["arm"] not in selected


@pytest.mark.asyncio
async def test_the_desk_is_untouched(engine: AsyncEngine) -> None:
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
        pullback_keys = await connection.scalar(
            text(
                "SELECT count(*) FROM meme_rule_sets WHERE id <> :a "
                "AND (params -> 'entry_pullback_pct' IS NOT NULL OR params -> 'entry_pullback_window_s' IS NOT NULL)"
            ),
            {"a": ARM},
        )
    assert desk == ["operator/5", "operator/6"]
    assert pullback_keys == 0, "no other set waits for a pullback"


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0063_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


def test_the_upgrade_refuses_without_an_active_operator_5(upgraded: str) -> None:
    config = alembic_config(upgraded)
    target: dict[str, object] = {"d": OPERATOR_5}
    retire = (
        "UPDATE meme_rule_sets SET status = 'retired', retired_at = now() WHERE id = :d",
        target,
    )
    revive = (
        "UPDATE meme_rule_sets SET status = 'active', retired_at = NULL WHERE id = :d",
        target,
    )
    try:
        command.downgrade(config, PREVIOUS)
        asyncio.run(_write(upgraded, [retire]))
        with pytest.raises(DBAPIError, match="operator/5 is missing or not active"):
            command.upgrade(config, REVISION)
        assert _revision_of(upgraded) == PREVIOUS and _count_of(upgraded, ARM) == 0
    finally:
        asyncio.run(_write(upgraded, [revive]))
        command.upgrade(config, REVISION)
    assert _revision_of(upgraded) == REVISION and _count_of(upgraded, ARM) == 1


@pytest.mark.parametrize(
    ("clock_sql", "message"),
    [
        ('params || \'{"clock": "1m"}\'::jsonb', "operator/5 is not on the 15s clock"),
        ("params - 'clock'", "operator/5 is not on the 15s clock"),
        ("params || '{\"clock\": null}'::jsonb", "operator/5 is not on the 15s clock"),
    ],
)
def test_the_upgrade_refuses_when_operator_5_is_not_on_the_15s_clock(
    upgraded: str, clock_sql: str, message: str
) -> None:
    """database-architect (review of T4.91): the arm copies operator/5's clock;
    anything but ``15s`` would plant a pullback set the Lab cannot load
    (``entry_pullback_of`` refuses another clock) — refused by name, nothing
    seeded, the revision stays ``0062``."""
    config = alembic_config(upgraded)
    target: dict[str, object] = {"d": OPERATOR_5}
    saved = asyncio.run(
        _scalar(upgraded, "SELECT params::text FROM meme_rule_sets WHERE id = :d", d=OPERATOR_5)
    )
    move = (f"UPDATE meme_rule_sets SET params = {clock_sql} WHERE id = :d", target)  # noqa: S608
    restore_params: dict[str, object] = {"d": OPERATOR_5, "p": saved}
    restore = ("UPDATE meme_rule_sets SET params = CAST(:p AS jsonb) WHERE id = :d", restore_params)
    try:
        command.downgrade(config, PREVIOUS)
        asyncio.run(_write(upgraded, [move]))
        with pytest.raises(DBAPIError, match=message):
            command.upgrade(config, REVISION)
        assert _revision_of(upgraded) == PREVIOUS and _count_of(upgraded, ARM) == 0
    finally:
        asyncio.run(_write(upgraded, [restore]))
        command.upgrade(config, REVISION)
    assert _revision_of(upgraded) == REVISION and _count_of(upgraded, ARM) == 1


def test_the_downgrade_refuses_while_a_proposal_or_a_bet_references_the_arm(
    upgraded: str,
) -> None:
    config = alembic_config(upgraded)
    proposal = "00000000-0000-4000-8000-000000006311"
    bet = "00000000-0000-4000-8000-000000006312"
    guarded: list[tuple[list[tuple[str, dict[str, object]]], str]] = [
        (
            [(_APPROVED, {"id": proposal, "rule_set": ARM})],
            "proposals reference the seeded recuo_v1 set - they carry EXP-M24's "
            "entry_pullback blocks and cannot be removed under them",
        ),
        (
            [
                (_APPROVED, {"id": proposal, "rule_set": OPERATOR_6}),
                (_A_BET, {"id": bet, "proposal": proposal, "rule_set": ARM}),
            ],
            "bets reference the seeded recuo_v1 set",
        ),
        (
            [(_A_REFUSAL, {"rule_set": ARM})],
            "refusal rows reference the seeded recuo_v1 set - they are EXP-M24's "
            "armed/no_pullback counterfactuals and cannot be removed under them",
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
        assert _count_of(upgraded, ARM) == 0 and _count_of(upgraded, OPERATOR_5) == 1
    finally:
        command.upgrade(config, REVISION)
    assert _revision_of(upgraded) == REVISION and _count_of(upgraded, ARM) == 1
