"""``0060_meme_refused_probe_arm`` (T4.85, EXP-M23) — its own file and its own
database, ``test_migration_0058.py``'s own shape: the two lines this revision
owes ``test_migrations.py`` (``HEAD_REVISION`` and the active-set count,
23 → 24) are changed there too, and nothing here depends on them.

What is proved: the arm exists (``research_only`` under EXP-M23, active, on
its **own** clock ``refused`` — never ``15s`` (which the fast lane and the
event lane read) and never ``event`` (the launch lane's marker)); its exit
parameters are the **desk's**, key by key, and not ``flow_v2``'s 3× / 1800 s,
which is caveat nº 1 of R67; subtracting the six keys this arm owns leaves
``operator/6`` byte for byte; every decimal is a string; the params load the
way the worker loads them and the worker's own loader returns the arm beside
the desk; the desk itself is untouched; and the downgrade removes the seed on
a clean database and refuses while a proposal or a bet references it (§17.7) —
which matters more here than in any previous arm, because a probe proposal's
``reasons`` is the only copy of that mint's refusal reasons, its stratum and
its inclusion probability.
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
from hunter_meme_worker.refused_probe import PROBE_CLOCK

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database

pytestmark = pytest.mark.integration

REVISION = "0060_meme_refused_probe_arm"
PREVIOUS = "0059_market_events"

PROBE = "01994d00-6c1a-7000-8000-00000000001c"
OPERATOR_6 = "01994d00-6c1a-7000-8000-000000000019"

ARM_KEYS: tuple[str, ...] = (
    "clock",
    "gate_key",
    "gate_version",
    "max_open_positions",
    "daily_loss_cap_sol",
    "wallet_max_sol",
)
"""``ddl/meme_refused_probe_arm.REFUSED_PROBE_ARM_KEYS``, frozen here too: drop
these six from both rows and what is left must be ``operator/6``."""

DESK_EXIT_KEYS: tuple[str, ...] = (
    "exit_key",
    "exit_version",
    "size_sol",
    "target_x",
    "trailing_pct",
    "trailing_arm_x",
    "max_hold_s",
    "max_loss_pct",
    "exit_on_line_break",
    "line_break_snapshots",
    "fee_pct",
    "priority_fee_sol",
    "max_sol_per_bet",
    "max_exposure_per_mint_sol",
)
""""Os parâmetros de saída são os da mesa real", as a list of keys."""

_A_PROPOSAL = (
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at, "
    "  decision, decided_by, decided_at) VALUES (:id, 'GUARD_MINT_60', :rule_set, 'operator', "
    "  'approved', now() + interval '2 minutes', '{}'::jsonb, 'user', now())"
)
_A_BET = (
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, entry_at, entry, "
    "  initial_risk_sol, params) VALUES (:id, :proposal, :rule_set, 'GUARD_MINT_60', 'paper', "
    "  now(), '{}'::jsonb, 0.07, '{}'::jsonb)"
)
_CLEAN: tuple[str, ...] = (
    "DELETE FROM meme_paper_bets WHERE mint = 'GUARD_MINT_60'",
    "DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT_60'",
)


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0060"))


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


def test_the_revision_lands_on_0059_and_fits_the_version_column() -> None:
    source = (REPO_ROOT / "infra" / "migrations" / "versions" / f"{REVISION}.py").read_text(
        encoding="utf-8"
    )
    assert f'revision: str = "{REVISION}"' in source
    assert f'down_revision: str | None = "{PREVIOUS}"' in source
    assert len(REVISION) <= 32


def test_only_an_operator_set_reaches_the_executor_so_this_arm_is_paper() -> None:
    """The arm is paper by construction, not by a flag someone can flip."""
    source = (
        REPO_ROOT / "services" / "meme-executor" / "hunter_meme_executor" / "auto_approve.py"
    ).read_text(encoding="utf-8")
    assert "\"WHERE rs.kind = 'operator' AND rs.status = 'active' \"" in source


@pytest.mark.asyncio
async def test_the_arm_is_seeded_on_its_own_clock_with_the_desks_exit(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as connection:
        seeded = await connection.scalar(
            text(
                "SELECT name || '/' || version || ':' || kind || ':' "
                "|| coalesce(exp_ref, '-') || ':' || status || ':' || (params ->> 'clock') "
                "|| ':' || (params ->> 'gate_key') || '/' || (params ->> 'gate_version') "
                "|| ':' || (params ->> 'exit_key') "
                "|| ':' || (params ->> 'size_sol') || '/' || jsonb_typeof(params -> 'size_sol') "
                "|| ':' || (params ->> 'target_x') || ':' || (params ->> 'trailing_pct') "
                "|| ':' || coalesce(params ->> 'trailing_arm_x', 'null') "
                "|| ':' || (params ->> 'max_hold_s') || ':' || (params ->> 'fee_pct') "
                "|| ':' || (params ->> 'exit_on_line_break') "
                "|| ':' || (params ->> 'max_open_positions') || ':' || (params ->> 'ttl_s') "
                "FROM meme_rule_sets WHERE id = :r"
            ),
            {"r": PROBE},
        )
    assert seeded == (
        "refused_probe_v0/1:research_only:EXP-M23:active:refused"
        ":recusadas_da_mesa/1:alvo_1_15x_trailing_10_tempo_5m"
        ":0.07/string:1.15:10:null:300:1.75:true:25:180"
    )


@pytest.mark.asyncio
async def test_the_exit_is_the_desks_key_by_key_never_flow_v2s(engine: AsyncEngine) -> None:
    """R67's caveat nº 1, as an assertion: ``flow_v2`` tests under 3× / 1800 s
    / trailing 35 % armed at 1,5×, which is **not** the policy the desk runs."""
    async with engine.connect() as connection:
        rows = {
            row[0]: (row[1], row[2])
            for row in await connection.execute(
                text(
                    "SELECT k, p.params ->> k, d.params ->> k "
                    "FROM unnest(CAST(:keys AS text[])) AS k, "
                    "     meme_rule_sets p, meme_rule_sets d "
                    "WHERE p.id = :p AND d.id = :d"
                ),
                {"keys": list(DESK_EXIT_KEYS), "p": PROBE, "d": OPERATOR_6},
            )
        }
    assert rows, "the two rows must exist"
    assert [key for key, (mine, desk) in rows.items() if mine != desk] == []
    assert rows["target_x"][0] == "1.15" and rows["max_hold_s"][0] == "300"
    assert rows["trailing_pct"][0] == "10" and rows["trailing_arm_x"][0] is None
    assert rows["size_sol"][0] == "0.07" and rows["exit_on_line_break"][0] == "true"


@pytest.mark.asyncio
async def test_minus_the_six_keys_it_owns_the_arm_is_the_desk(engine: AsyncEngine) -> None:
    """The whole design, as one assertion: the population differs, nothing
    else does except the paper bankroll that keeps the sample from being a
    measurement of its own ceilings."""
    async with engine.connect() as connection:
        same = await connection.scalar(
            text(
                "SELECT (p.params - CAST(:keys AS text[]) = d.params - CAST(:keys AS text[]))::text "
                "FROM meme_rule_sets p, meme_rule_sets d WHERE p.id = :p AND d.id = :d"
            ),
            {"keys": list(ARM_KEYS), "p": PROBE, "d": OPERATOR_6},
        )
        numbers = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT key FROM meme_rule_sets, jsonb_each(params) "
                    "WHERE id = :p AND jsonb_typeof(value) = 'number' ORDER BY key"
                ),
                {"p": PROBE},
            )
        ]
    assert same == "true"
    assert numbers == sorted(
        [
            "exit_version",
            "gate_version",
            "line_break_snapshots",
            "max_age_s",
            "max_hold_s",
            "max_open_positions",
            "min_age_s",
            "min_unique_buyers",
            "max_snipers",
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
    row = await _spec_row(engine, PROBE)
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
    assert (spec.kind, spec.clock, spec.exp_ref) == ("research_only", PROBE_CLOCK, "EXP-M23")
    assert (spec.size_sol, spec.max_sol_per_bet, spec.max_exposure_per_mint_sol) == (
        Decimal("0.07"),
    ) * 3
    assert (spec.target_x, spec.trailing_pct, spec.trailing_arm_x, spec.max_hold_s) == (
        Decimal("1.15"),
        Decimal("10"),
        None,
        300,
    )
    assert (spec.max_open_positions, spec.ttl_s, spec.exit_on_line_break) == (25, 180, True)
    assert (spec.wallet_max_sol, spec.daily_loss_cap_sol) == (Decimal("100.0"), Decimal("10.0"))
    assert (spec.fee_pct, spec.max_loss_pct) == (Decimal("1.75"), Decimal("50"))
    effective = effective_params(spec, {})
    assert not isinstance(effective, str), effective
    rules = effective.exit_rules()
    assert rules.target_multiple == Decimal("1.15")
    assert rules.trailing_drawdown_pct == Decimal("10")
    assert rules.trailing_arm_multiple is None
    assert rules.time_stop_s == 300
    assert rules.exit_on_line_break is True


@pytest.mark.asyncio
async def test_the_worker_loader_returns_the_arm_and_no_gate_step_selects_it(
    engine: AsyncEngine,
) -> None:
    """``load_active_rule_sets`` must keep loading it — the fill, the marks and
    the exits are the Lab's own, which is EXP-M23's required symmetry — while
    its clock belongs to no existing step (``1m``, ``15s``, ``event``)."""
    async with AsyncSession(engine) as session:
        specs = await load_active_rule_sets(session)
    by_label = {spec.label: spec for spec in specs}
    assert {"refused_probe_v0/1", "operator/6"} <= set(by_label)
    assert by_label["refused_probe_v0/1"].clock == PROBE_CLOCK
    assert PROBE_CLOCK not in {"1m", "15s", "event"}
    assert [s.label for s in specs if s.clock == "1m" and s.id == PROBE] == []
    assert [s.label for s in specs if s.clock == "15s" and s.id == PROBE] == []
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
                "SELECT (params ->> 'clock') || ':' || (params ->> 'max_open_positions') "
                "|| ':' || (params ->> 'daily_loss_cap_sol') || ':' || (params ->> 'wallet_max_sol')"
                " || ':' || (params ->> 'gate_key') FROM meme_rule_sets WHERE id = :r"
            ),
            {"r": OPERATOR_6},
        )
    assert desk == ["operator/5", "operator/6"]
    assert six == "15s:2:0.20:2.0:fluxo_e_holders"


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0060_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


def test_the_downgrade_refuses_while_a_proposal_or_a_bet_references_the_arm(
    upgraded: str,
) -> None:
    config = alembic_config(upgraded)
    proposal = "00000000-0000-4000-8000-000000006001"
    bet = "00000000-0000-4000-8000-000000006002"
    guarded: list[tuple[list[tuple[str, dict[str, object]]], str]] = [
        (
            [(_A_PROPOSAL, {"id": proposal, "rule_set": PROBE})],
            "proposals reference the seeded refused_probe_v0 set - they carry "
            "EXP-M23's inclusion probabilities and cannot be removed under them",
        ),
        (
            [
                (_A_PROPOSAL, {"id": proposal, "rule_set": OPERATOR_6}),
                (_A_BET, {"id": bet, "proposal": proposal, "rule_set": PROBE}),
            ],
            "bets reference the seeded refused_probe_v0 set",
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
        assert asyncio.run(_count_of(upgraded, PROBE)) == 0
        assert asyncio.run(_count_of(upgraded, OPERATOR_6)) == 1
    finally:
        command.upgrade(config, REVISION)
    assert asyncio.run(_revision_of(upgraded)) == REVISION
    assert asyncio.run(_count_of(upgraded, PROBE)) == 1
