"""``0058_meme_gate_absorb_arm`` (T4.79, EXP-M22) — its own file and its own
database, ``test_migration_0054.py``'s own shape: the two lines this revision
owes ``test_migrations.py`` (``HEAD_REVISION`` and ``0022``'s active-set count,
21 → 23) are changed there too, and nothing here depends on them.

What is proved: the two arms exist (``research_only`` under EXP-M22, active, on
the 15-second clock — the event lane's own filter — never ``clock = 'event'``,
the launch lane's marker); they differ by exactly one key each (the treatment's
``require_absorb_confirmed``, the control's ``require_absorb_sell_seen``) and
are byte for byte identical otherwise; every decimal is a string; the params
load the way the worker loads them (``RuleSetSpec.from_params`` reads the two
switches, ``effective_params(...).exit_rules()`` is the desk's rule) and the
worker's own loader query returns both; the downgrade removes them on a clean
database and refuses while a proposal or a bet references either (§17.7).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.lab_params import effective_params
from hunter_meme_worker.lab_repo import load_active_rule_sets

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database

pytestmark = pytest.mark.integration

REVISION = "0058_meme_gate_absorb_arm"
PREVIOUS = "0057_spot_desk"

TREATMENT = "01994d00-6c1a-7000-8000-00000000001a"
CONTROL = "01994d00-6c1a-7000-8000-00000000001b"
OPERATOR_6 = "01994d00-6c1a-7000-8000-000000000019"

_A_PROPOSAL = (
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at, "
    "  decision, decided_by, decided_at) VALUES (:id, 'GUARD_MINT_58', :rule_set, 'operator', "
    "  'approved', now() + interval '2 minutes', '{}'::jsonb, 'user', now())"
)
_A_BET = (
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, entry_at, entry, "
    "  initial_risk_sol, params) VALUES (:id, :proposal, :rule_set, 'GUARD_MINT_58', 'paper', "
    "  now(), '{}'::jsonb, 0.07, '{}'::jsonb)"
)
_CLEAN: tuple[str, ...] = (
    "DELETE FROM meme_paper_bets WHERE mint = 'GUARD_MINT_58'",
    "DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT_58'",
)


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0058"))


@pytest.fixture(scope="module")
def upgraded(db_url: str) -> Iterator[str]:
    """This revision by name, not ``head``: the day another lands on top this
    module's downgrade assertions keep being about this one step."""
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


def test_the_revision_lands_on_0057_and_fits_the_version_column() -> None:
    source = (REPO_ROOT / "infra" / "migrations" / "versions" / f"{REVISION}.py").read_text(
        encoding="utf-8"
    )
    assert f'revision: str = "{REVISION}"' in source
    assert f'down_revision: str | None = "{PREVIOUS}"' in source
    assert len(REVISION) <= 32


def test_only_an_operator_set_reaches_the_executor_so_a_research_arm_is_paper() -> None:
    source = (
        REPO_ROOT / "services" / "meme-executor" / "hunter_meme_executor" / "auto_approve.py"
    ).read_text(encoding="utf-8")
    assert "\"WHERE rs.kind = 'operator' AND rs.status = 'active' \"" in source


@pytest.mark.asyncio
async def test_the_two_arms_are_seeded_on_the_15s_clock_with_one_switch_each(
    engine: AsyncEngine,
) -> None:
    """Both ``research_only`` under EXP-M22, active, ``clock = 15s`` (never the
    launch lane's ``event``), the desk's ticket/exit, the fee R62/R64 measured,
    and exactly one absorption switch each."""
    async with engine.connect() as connection:
        seeded = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT name || '/' || version || ':' || kind || ':' "
                    "|| coalesce(exp_ref, '-') || ':' || status || ':' || (params ->> 'clock') "
                    "|| ':' || (params ->> 'gate_key') || '/' || (params ->> 'gate_version') "
                    "|| ':' || (params ->> 'exit_key') "
                    "|| ':' || (params ->> 'size_sol') || '/' || jsonb_typeof(params -> 'size_sol') "
                    "|| ':' || (params ->> 'target_x') || ':' || (params ->> 'trailing_pct') "
                    "|| ':' || coalesce(params ->> 'trailing_arm_x', 'null') "
                    "|| ':' || (params ->> 'max_hold_s') || ':' || (params ->> 'fee_pct') "
                    "|| ':' || (params ->> 'max_open_positions') || ':' || (params ->> 'ttl_s') "
                    "|| ':' || (params ->> 'min_age_s') || '-' || (params ->> 'max_age_s') "
                    "|| ':' || coalesce(params ->> 'require_absorb_confirmed', '-') "
                    "|| ':' || coalesce(params ->> 'require_absorb_sell_seen', '-') "
                    "|| ':' || (params ->> 'require_progress') "
                    "|| ':' || (params ->> 'require_creator_not_net_seller') "
                    "|| ':' || (params ->> 'exclude_mayhem') "
                    "FROM meme_rule_sets WHERE id IN (:a, :b) ORDER BY version"
                ),
                {"a": TREATMENT, "b": CONTROL},
            )
        ]
    shared = (
        ":research_only:EXP-M22:active:15s:absorcao_de_venda/1:alvo_1_15x_trailing_10_tempo_5m"
        ":0.07/string:1.15:10:null:300:1.25:3:180:30-300"
    )
    assert seeded == [
        f"absorb_v0/1{shared}:true:-:false:false:true",
        f"absorb_v0/2{shared}:-:true:false:false:true",
    ]


@pytest.mark.asyncio
async def test_the_arms_differ_by_exactly_one_key_each_and_every_decimal_is_a_string(
    engine: AsyncEngine,
) -> None:
    """The whole experiment, as an assertion: drop each arm's own switch and
    the two are the same params byte for byte; no value is a JSON number
    that should be a decimal (the Lab refuses a bare float, T4.64)."""
    async with engine.connect() as connection:
        same = await connection.scalar(
            text(
                "SELECT ((t.params - 'require_absorb_confirmed') "
                "= (c.params - 'require_absorb_sell_seen'))::text "
                "|| ':' || (t.params ? 'require_absorb_sell_seen')::text "
                "|| ':' || (c.params ? 'require_absorb_confirmed')::text "
                "FROM meme_rule_sets t, meme_rule_sets c WHERE t.id = :t AND c.id = :c"
            ),
            {"t": TREATMENT, "c": CONTROL},
        )
        numbers = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT key FROM meme_rule_sets, jsonb_each(params) "
                    "WHERE id = :t AND jsonb_typeof(value) = 'number' ORDER BY key"
                ),
                {"t": TREATMENT},
            )
        ]
    assert same == "true:false:false"
    assert numbers == sorted(
        [
            "gate_version",
            "exit_version",
            "line_break_snapshots",
            "max_age_s",
            "max_hold_s",
            "max_open_positions",
            "min_age_s",
            "ttl_s",
        ]
    ), "only counts and seconds are JSON numbers; every SOL/percent/multiple is a string"


async def _spec_row(engine: AsyncEngine, rule_set: str) -> dict[str, Any]:
    async with engine.connect() as connection:
        return dict(
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


@pytest.mark.asyncio
async def test_the_params_load_the_way_the_worker_loads_them(engine: AsyncEngine) -> None:
    """``meme_rule_set.py --validate``, as a test: the seeded ``params`` go
    through ``RuleSetSpec.from_params`` (the gate and the two switches) and
    ``effective_params(spec, {}).exit_rules()`` — the desk's own rule."""
    for rule_set, confirmed, sell_seen in ((TREATMENT, True, False), (CONTROL, False, True)):
        row = await _spec_row(engine, rule_set)
        spec = RuleSetSpec.from_params(
            id=row["id"],
            name=row["name"],
            version=row["version"],
            kind=row["kind"],
            exp_ref=row["exp_ref"],
            status=row["status"],
            code_ref=row["code_ref"],
            params=row["params"],
        )
        assert (spec.kind, spec.clock, spec.exp_ref) == ("research_only", "15s", "EXP-M22")
        assert (spec.require_absorb_confirmed, spec.require_absorb_sell_seen) == (
            confirmed,
            sell_seen,
        )
        assert (spec.size_sol, spec.max_sol_per_bet, spec.max_exposure_per_mint_sol) == (
            Decimal("0.07"),
        ) * 3
        assert (spec.target_x, spec.trailing_pct, spec.trailing_arm_x, spec.max_hold_s) == (
            Decimal("1.15"),
            Decimal("10"),
            None,
            300,
        )
        assert (spec.max_open_positions, spec.ttl_s, spec.exit_on_line_break) == (3, 180, True)
        assert (spec.fee_pct, spec.max_loss_pct) == (Decimal("1.25"), Decimal("50"))
        assert (spec.pedigree_exclusions, spec.pedigree_e2b, spec.declares_mayhem) == (
            True,
            False,
            True,
        )
        gate = spec.gate
        assert (gate.min_age_s, gate.max_age_s) == (30, 300)
        assert not gate.require_progress and not gate.require_creator_not_net_seller
        assert gate.exclude_mayhem and gate.max_participation_pct == Decimal("1")
        assert gate.min_unique_buyers is None and gate.max_snipers is None
        assert gate.min_early_retention_pct is None and gate.max_recent_drawdown_pct is None
        effective = effective_params(spec, {})
        assert not isinstance(effective, str), effective
        rules = effective.exit_rules()
        assert rules.target_multiple == Decimal("1.15")
        assert rules.trailing_drawdown_pct == Decimal("10")
        assert rules.trailing_arm_multiple is None
        assert rules.time_stop_s == 300
        assert rules.exit_on_line_break is True


@pytest.mark.asyncio
async def test_the_worker_loader_returns_both_arms_beside_the_desk(engine: AsyncEngine) -> None:
    """``lab_repo.load_active_rule_sets`` (the query the Lab tick runs, T4.67c's
    ``clock <> 'event'`` filter included) parses every active set — the two
    arms among them, on the 15-second clock the event lane keeps."""
    async with AsyncSession(engine) as session:
        specs = await load_active_rule_sets(session)
    by_label = {spec.label: spec for spec in specs}
    assert {"absorb_v0/1", "absorb_v0/2", "operator/6", "flow_v2/10"} <= set(by_label)
    assert [by_label[label].clock for label in ("absorb_v0/1", "absorb_v0/2")] == ["15s", "15s"]
    assert "launch_v0/1" not in by_label, "the launch lane's own set never reaches this loader"


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
        six = await connection.scalar(
            text(
                "SELECT (params ? 'require_absorb_confirmed')::text FROM meme_rule_sets WHERE id = :r"
            ),
            {"r": OPERATOR_6},
        )
    assert desk == ["operator/5", "operator/6"]
    assert six == "false"


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0058_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


def test_the_downgrade_refuses_while_a_proposal_or_a_bet_references_an_arm(
    upgraded: str,
) -> None:
    config = alembic_config(upgraded)
    proposal = "00000000-0000-4000-8000-000000005801"
    bet = "00000000-0000-4000-8000-000000005802"
    guarded: list[tuple[list[tuple[str, dict[str, object]]], str]] = [
        (
            [(_A_PROPOSAL, {"id": proposal, "rule_set": TREATMENT})],
            "proposals reference a seeded absorb_v0 set",
        ),
        (
            [
                (_A_PROPOSAL, {"id": proposal, "rule_set": OPERATOR_6}),
                (_A_BET, {"id": bet, "proposal": proposal, "rule_set": CONTROL}),
            ],
            "bets reference a seeded absorb_v0 set",
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


def test_the_downgrade_removes_the_seeds_on_a_clean_database_and_comes_back(
    upgraded: str,
) -> None:
    config = alembic_config(upgraded)
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_revision_of(upgraded)) == PREVIOUS
        assert asyncio.run(_count_of(upgraded, TREATMENT)) == 0
        assert asyncio.run(_count_of(upgraded, CONTROL)) == 0
        assert asyncio.run(_count_of(upgraded, OPERATOR_6)) == 1
    finally:
        command.upgrade(config, REVISION)
    assert asyncio.run(_revision_of(upgraded)) == REVISION
    assert asyncio.run(_count_of(upgraded, TREATMENT)) == 1
    assert asyncio.run(_count_of(upgraded, CONTROL)) == 1
