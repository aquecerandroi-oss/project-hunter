"""``0055_meme_operator6_desk`` (T4.71) — its own file and its own database,
``test_migration_0054.py``'s shape: the lines this revision owes
``test_migrations.py`` (``HEAD_REVISION``, ``0022``'s active-set count 20 → 21,
and every "the desk is ``operator/5`` alone" assertion taken at ``head``) are
changed there too, and nothing here depends on them.

What is proved: the seed exists, ``kind = 'operator'``, active, 15-second
clock, with Everton's exit and the desk's ticket as **strings** where decimal;
its ``params`` load through ``RuleSetSpec.from_params`` and build the exit
rules (the exact path ``meme_rule_set.py --validate`` runs, T4.64) with the
gate ``fluxo_e_holders/1``; it equals ``flow_v2/1`` on **every** key outside
the twelve desk keys — i.e. on every entry key; the executor's selection
picks any active ``operator`` set and the two brakes are executor-level; the
downgrade removes it on a clean database and refuses while a proposal, a bet
or — through the proposal — a **real order or position** references it
(§17.7).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from decimal import Decimal

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.lab_params import effective_params

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database, migration_ddl

pytestmark = pytest.mark.integration

REVISION = "0055_meme_operator6_desk"
PREVIOUS = "0054_meme_gate_crowd_arm"

OPERATOR_6_RULE_SET = "01994d00-6c1a-7000-8000-000000000019"
OPERATOR_5_RULE_SET = "01994d00-6c1a-7000-8000-000000000011"
FLOW_V2_1_RULE_SET = "01994d00-6c1a-7000-8000-000000000008"
"""``flow_v2/1`` (``0030``, EXP-M5) — the entry this desk buys with."""

_A_PROPOSAL = (
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at, "
    "  decision, decided_by, decided_at, mode) VALUES (:id, 'GUARD_MINT_55', :rule_set, "
    "  'operator', 'approved', now() + interval '2 minutes', '{}'::jsonb, 'user', now(), :mode)"
)
_A_BET = (
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, entry_at, entry, "
    "  initial_risk_sol, params) VALUES (:id, :proposal, :rule_set, 'GUARD_MINT_55', 'paper', "
    "  now(), '{}'::jsonb, 0.07, '{}'::jsonb)"
)
_A_LIVE_ORDER = (
    "INSERT INTO meme_live_orders (id, proposal_id, side, client_order_id, status, "
    "  tx_signature, signatures, fill) VALUES (:id, :proposal, 'buy', :key, 'confirmed', "
    "  :signature, CAST(:signatures AS jsonb), '{}'::jsonb)"
)
_A_LIVE_POSITION = (
    "INSERT INTO meme_live_positions (id, proposal_id, entry_order_id, mint, status, entry_at, "
    "  entry, tokens, sol_spent_lamports, initial_risk_sol, params) "
    "VALUES (:id, :proposal, :order, 'GUARD_MINT_55', 'open', now() - interval '1 minute', "
    "  '{}'::jsonb, 1000, 70000000, 0.07, '{}'::jsonb)"
)
_CLEAN: tuple[str, ...] = (
    "DELETE FROM meme_live_positions WHERE mint = 'GUARD_MINT_55'",
    "DELETE FROM meme_live_orders WHERE proposal_id IN "
    "  (SELECT id FROM meme_proposals WHERE mint = 'GUARD_MINT_55')",
    "DELETE FROM meme_paper_bets WHERE mint = 'GUARD_MINT_55'",
    "DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT_55'",
)


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0055"))


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


def test_the_revision_lands_on_0054_and_fits_the_version_column() -> None:
    """Pure: no database, no container — the chain this task was told to extend,
    and the 32-character ceiling of ``alembic_version.version_num`` (§30.7)."""
    source = (REPO_ROOT / "infra" / "migrations" / "versions" / f"{REVISION}.py").read_text(
        encoding="utf-8"
    )
    assert f'revision: str = "{REVISION}"' in source
    assert f'down_revision: str | None = "{PREVIOUS}"' in source
    assert len(REVISION) <= 32


def test_the_overrides_and_the_desk_keys_are_the_same_twelve() -> None:
    """Pure: the constant the seed composes and the tuple the byte-for-byte
    test subtracts name exactly the same keys — the docstring's claim that
    "everything else is ``flow_v2/1``'s" is only as good as this."""
    ddl = migration_ddl("meme_operator_6")
    overrides = json.loads("{" + ddl.OPERATOR_6_OVERRIDES + "}")
    assert set(overrides) == set(ddl.OPERATOR_6_DESK_KEYS)
    assert len(ddl.OPERATOR_6_DESK_KEYS) == 12
    assert overrides["trailing_arm_x"] is None
    for key in ("target_x", "trailing_pct", "size_sol", "max_sol_per_bet"):
        assert isinstance(overrides[key], str), f"{key}: decimals are strings"


def test_the_executor_opens_any_active_operator_set_and_the_brakes_are_shared() -> None:
    """Read from the code, not assumed: ``auto_approve`` selects proposals of
    **any** active ``operator`` set (no name, no version), so ``operator/6``
    reaches money the moment it is seeded; and the two brakes the decision
    calls shared — open positions and the daily loss cap — are counted by the
    risk engine against ``MemeLimits`` (the executor's env), never per set."""
    executor = REPO_ROOT / "services" / "meme-executor" / "hunter_meme_executor"
    auto_approve = (executor / "auto_approve.py").read_text(encoding="utf-8")
    assert "\"WHERE rs.kind = 'operator' AND rs.status = 'active' \"" in auto_approve
    assert "rs.name" not in auto_approve and "rs.version" not in auto_approve
    wallet = (
        REPO_ROOT / "packages" / "risk-core" / "hunter_risk_meme" / "checks_wallet.py"
    ).read_text(encoding="utf-8")
    assert "limits.max_open_positions" in wallet
    assert "limits.daily_loss_cap_sol" in wallet
    assert "rule_set" not in wallet, "the brakes never look at which set opened the position"


@pytest.mark.asyncio
async def test_the_desk_is_seeded_with_everton_s_exit_and_the_ticket(engine: AsyncEngine) -> None:
    """``operator/6``: ``operator``, no ``exp_ref``, active, 15-second clock,
    gate ``fluxo_e_holders/1`` (``flow_v2/1``'s, not arm 2's), the exit
    ``1.15×`` / trailing 10 % armed from the entry / 300 s, the 0,07 ticket,
    two positions, 180 s for the desk, the repeat-dumper switch — decimals as
    JSON **strings**, ``trailing_arm_x`` as JSON ``null``."""
    async with engine.connect() as connection:
        seeded = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT name || '/' || version || ':' || kind || ':' "
                    "|| coalesce(exp_ref, '-') || ':' || status || ':' || (params ->> 'clock') "
                    "|| ':' || (params ->> 'gate_key') || '/' || (params ->> 'gate_version') "
                    "|| ':' || (params ->> 'exit_key') "
                    "|| ':' || (params ->> 'target_x') || '/' || jsonb_typeof(params -> 'target_x') "
                    "|| ':' || (params ->> 'trailing_pct') "
                    "|| '/' || jsonb_typeof(params -> 'trailing_pct') "
                    "|| ':' || jsonb_typeof(params -> 'trailing_arm_x') "
                    "|| ':' || (params ->> 'max_hold_s') "
                    "|| '/' || jsonb_typeof(params -> 'max_hold_s') "
                    "|| ':' || (params ->> 'exit_on_line_break') "
                    "|| ':' || (params ->> 'size_sol') || '/' || jsonb_typeof(params -> 'size_sol') "
                    "|| ':' || (params ->> 'max_sol_per_bet') "
                    "|| ':' || (params ->> 'max_exposure_per_mint_sol') "
                    "|| ':' || (params ->> 'max_open_positions') "
                    "|| ':' || (params ->> 'ttl_s') "
                    "|| ':' || (params ->> 'pedigree_repeat_dumper') "
                    "|| ':' || (params ->> 'max_loss_pct') "
                    "|| ':' || (params ->> 'max_snipers') "
                    "|| ':' || coalesce(params ->> 'min_holders', '-') "
                    "FROM meme_rule_sets WHERE id = :r"
                ),
                {"r": OPERATOR_6_RULE_SET},
            )
        ]
    assert seeded == [
        "operator/6:operator:-:active:15s:fluxo_e_holders/1:alvo_1_15x_trailing_10_tempo_5m"
        ":1.15/string:10/string:null:300/number:true:0.07/string:0.07:0.07:2:180:true:50:2:-"
    ], (
        "flow_v2/1's E1 gate (version 1, 2 snipers, no min_holders) with Everton's exit "
        "and the desk's 0,07 ticket"
    )


@pytest.mark.asyncio
async def test_the_desk_equals_flow_v2_1_on_every_entry_key(engine: AsyncEngine) -> None:
    """The whole desk, as an assertion: subtract the twelve desk keys from both
    rows and what is left — every entry key, the wallet ceilings, the loss
    floor, the fee — is byte for byte ``flow_v2/1``'s. Read against the
    **seeded** ``flow_v2/1`` (this database was never ``--set-param``'d)."""
    ddl = migration_ddl("meme_operator_6")
    minus = " ".join(f"- '{k}'" for k in ddl.OPERATOR_6_DESK_KEYS)
    async with engine.connect() as connection:
        rows = [
            row[0]
            for row in await connection.execute(
                text(
                    f"SELECT ((o.params {minus}) = (f.params {minus}))::text"  # noqa: S608
                    " || ':' || (o.params ->> 'gate_key' = f.params ->> 'gate_key')::text"
                    " || ':' || (o.params -> 'gate_version' = f.params -> 'gate_version')::text"
                    " || ':' || (o.params ->> 'max_snipers' = f.params ->> 'max_snipers')::text"
                    " || ':' || (o.params ->> 'min_unique_buyers' "
                    "             = f.params ->> 'min_unique_buyers')::text"
                    " FROM meme_rule_sets o, meme_rule_sets f WHERE o.id = :o AND f.id = :f"
                ),
                {"o": OPERATOR_6_RULE_SET, "f": FLOW_V2_1_RULE_SET},
            )
        ]
    assert rows == ["true:true:true:true:true"], (
        "operator/6 minus the twelve desk keys is flow_v2/1 minus the same twelve, byte for byte"
    )


@pytest.mark.asyncio
async def test_the_params_load_the_way_the_worker_loads_them(engine: AsyncEngine) -> None:
    """``meme_rule_set.py --validate operator/6``, as a test: the seeded
    ``params`` go through ``RuleSetSpec.from_params`` (the gate included) and
    ``effective_params(spec, {}).exit_rules()`` — the exact path the T4.64
    validator runs, and the one a bare float or an arm at 1× crash-looped the
    worker through on 18/09 (KB-0140)."""
    async with engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT id::text, name, version, kind, exp_ref, status, code_ref, params "
                        "FROM meme_rule_sets WHERE id = :r"
                    ),
                    {"r": OPERATOR_6_RULE_SET},
                )
            )
            .mappings()
            .one()
        )
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
    assert (spec.label, spec.kind, spec.clock) == ("operator/6", "operator", "15s")
    assert (spec.size_sol, spec.max_sol_per_bet, spec.max_exposure_per_mint_sol) == (
        Decimal("0.07"),
        Decimal("0.07"),
        Decimal("0.07"),
    )
    assert (spec.target_x, spec.trailing_pct, spec.trailing_arm_x, spec.max_hold_s) == (
        Decimal("1.15"),
        Decimal("10"),
        None,
        300,
    )
    assert (spec.max_open_positions, spec.ttl_s, spec.exit_on_line_break) == (2, 180, True)
    assert (spec.pedigree_repeat_dumper, spec.pedigree_exclusions) == (True, True)
    assert spec.max_loss_pct == Decimal("50")
    gate = spec.gate
    assert (gate.min_age_s, gate.max_age_s) == (30, 300)
    assert gate.min_unique_buyers == 10
    assert gate.max_sells_to_buys == Decimal("0.6")
    assert gate.max_snipers == 2
    assert gate.require_positive_flow and gate.require_holders_rising
    effective = effective_params(spec, {})
    assert not isinstance(effective, str), effective
    rules = effective.exit_rules()
    assert rules.target_multiple == Decimal("1.15")
    assert rules.trailing_drawdown_pct == Decimal("10")
    assert rules.trailing_arm_multiple is None
    assert rules.time_stop_s == 300
    assert rules.exit_on_line_break is True


@pytest.mark.asyncio
async def test_operator_5_stays_active_beside_operator_6(engine: AsyncEngine) -> None:
    """Nothing is retired: the desk now has **two** active operator sets, and
    the comparison between them is the point of the decision."""
    async with engine.connect() as connection:
        desk = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT name || '/' || version || ':' || status FROM meme_rule_sets "
                    "WHERE kind = 'operator' AND status = 'active' ORDER BY version"
                )
            )
        ]
        five = await connection.scalar(
            text("SELECT status FROM meme_rule_sets WHERE id = :r"), {"r": OPERATOR_5_RULE_SET}
        )
    assert desk == ["operator/5:active", "operator/6:active"]
    assert five == "active"


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    """``alembic check`` on a database of its own taken all the way to ``head``:
    this revision seeds data and changes no schema, so the comparison with the
    models has to stay empty."""
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0055_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


def test_the_downgrade_refuses_while_a_real_order_or_position_references_the_desk(
    upgraded: str,
) -> None:
    """§17.7, the loudest case first: a real order — and a real **open
    position** — under ``operator/6`` reaches the set only through its
    proposal, and the refusal names the order/position, never just the
    proposal. The position case fires its own guard: the entry order sits
    under an ``operator/5`` proposal (not guarded), the position under an
    ``operator/6`` one. Then the proposal and the paper bet, as ``0049``–``0054``."""
    config = alembic_config(upgraded)
    proposal = "00000000-0000-4000-8000-000000005501"
    other = "00000000-0000-4000-8000-000000005505"
    order = "00000000-0000-4000-8000-000000005502"
    position = "00000000-0000-4000-8000-000000005503"
    bet = "00000000-0000-4000-8000-000000005504"

    def live_order(under: str) -> tuple[str, dict[str, object]]:
        return (
            _A_LIVE_ORDER,
            {
                "id": order,
                "proposal": under,
                "key": f"meme:{under}",
                "signature": "sig55",
                "signatures": '["sig55"]',
            },
        )

    guarded: list[tuple[list[tuple[str, dict[str, object]]], str]] = [
        (
            [
                (_A_PROPOSAL, {"id": proposal, "rule_set": OPERATOR_6_RULE_SET, "mode": "live"}),
                live_order(proposal),
            ],
            "meme_live_orders rows exist - real orders were placed under the seeded operator/6",
        ),
        (
            [
                (_A_PROPOSAL, {"id": other, "rule_set": OPERATOR_5_RULE_SET, "mode": "live"}),
                (_A_PROPOSAL, {"id": proposal, "rule_set": OPERATOR_6_RULE_SET, "mode": "live"}),
                live_order(other),
                (_A_LIVE_POSITION, {"id": position, "proposal": proposal, "order": order}),
            ],
            "meme_live_positions rows exist - real positions exist under the seeded operator/6",
        ),
        (
            [(_A_PROPOSAL, {"id": proposal, "rule_set": OPERATOR_6_RULE_SET, "mode": "paper"})],
            "proposals reference the seeded operator/6 set",
        ),
        (
            [
                (_A_PROPOSAL, {"id": proposal, "rule_set": OPERATOR_5_RULE_SET, "mode": "paper"}),
                (_A_BET, {"id": bet, "proposal": proposal, "rule_set": OPERATOR_6_RULE_SET}),
            ],
            "bets reference the seeded operator/6 set",
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
    """The second desk goes and comes back; ``operator/5`` and ``flow_v2/1`` do
    not move."""
    config = alembic_config(upgraded)
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_revision_of(upgraded)) == PREVIOUS
        assert asyncio.run(_count_of(upgraded, OPERATOR_6_RULE_SET)) == 0, (
            "the seed is the whole revision: reversing it leaves no row behind"
        )
        assert asyncio.run(_count_of(upgraded, OPERATOR_5_RULE_SET)) == 1
        assert asyncio.run(_count_of(upgraded, FLOW_V2_1_RULE_SET)) == 1
    finally:
        # Back to REVISION, not "head": this module's database is staged at
        # REVISION on purpose (see the ``upgraded`` fixture).
        command.upgrade(config, REVISION)
    assert asyncio.run(_revision_of(upgraded)) == REVISION
    assert asyncio.run(_count_of(upgraded, OPERATOR_6_RULE_SET)) == 1
