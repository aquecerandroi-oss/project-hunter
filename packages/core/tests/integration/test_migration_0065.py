"""``0065_meme_pullback_control_arm`` (T4.95, EXP-M25) — its own file and its
own database, ``test_migration_0063.py``'s own shape: the two lines this
revision owes ``test_migrations.py`` (``HEAD_REVISION`` and the active-set
count, 25 → 26) are changed there too, and nothing here depends on them.

What is proved: the control exists (``research_only`` under EXP-M25, active,
on ``recuo_v1/1``'s ``15s`` clock); its document is ``recuo_v1/1``'s **minus
the two pullback keys and nothing else**, byte for byte, so the only
difference between the pair is *when* it enters; the params load the way the
worker loads them (no pullback, the same gate criterion by criterion, the same
exit); **the executor's own selection query never returns a proposal of this
arm** (run against the database, not grepped); the desk and ``recuo_v1/1`` are
untouched; the upgrade refuses without an active ``recuo_v1/1`` on the ``15s``
clock; and the downgrade removes the seed on a clean database and refuses while
a proposal, a bet, a param-history row or a sampled refusal references it.
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
from hunter_meme_worker.entry_pullback import PULLBACK_CONTROL_RULE_SET_ID
from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.lab_params import effective_params
from hunter_meme_worker.lab_repo import load_active_rule_sets

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database

pytestmark = pytest.mark.integration

REVISION = "0065_meme_pullback_control_arm"
PREVIOUS = "0064_meme_tokens_symbol_index"

CONTROL = "01994d00-6c1a-7000-8000-00000000001e"
ARM = "01994d00-6c1a-7000-8000-00000000001d"
OPERATOR_5 = "01994d00-6c1a-7000-8000-000000000011"
OPERATOR_6 = "01994d00-6c1a-7000-8000-000000000019"

PULLBACK_KEYS: tuple[str, ...] = ("entry_pullback_pct", "entry_pullback_window_s")
"""``ddl/meme_pullback_control_arm.PULLBACK_KEYS``, frozen here too."""

_PROPOSED = (
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, expires_at, "
    "  features_end_time) VALUES (:id, 'GUARD_MINT_65', :rule_set, 'rules', 'proposed', "
    "  CAST(:at AS timestamptz), CAST(:at AS timestamptz) + interval '3 minutes', "
    "  CAST(:at AS timestamptz))"
)
_APPROVED = (
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at, "
    "  decision, decided_by, decided_at) VALUES (:id, 'GUARD_MINT_65', :rule_set, 'operator', "
    "  'approved', now() + interval '2 minutes', '{}'::jsonb, 'user', now())"
)
_A_BET = (
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, entry_at, entry, "
    "  initial_risk_sol, params) VALUES (:id, :proposal, :rule_set, 'GUARD_MINT_65', 'paper', "
    "  now(), '{}'::jsonb, 0.07, '{}'::jsonb)"
)
_A_REFUSAL = (
    "INSERT INTO meme_gate_refusals_by_mint (as_of, rule_set_id, mint, refusal) "
    "VALUES (now(), :rule_set, 'GUARD_MINT_65', 'flow_not_positive')"
)
_A_PARAM_CHANGE = (
    "INSERT INTO meme_rule_set_param_history (id, rule_set_id, key, old_value, new_value, "
    "  changed_by, reason) VALUES (:id, :rule_set, 'max_hold_s', '300'::jsonb, '301'::jsonb, "
    "  'test', 'T4.95 guard')"
)
_CLEAN: tuple[str, ...] = (
    "DELETE FROM meme_gate_refusals_by_mint WHERE mint = 'GUARD_MINT_65'",
    "DELETE FROM meme_paper_bets WHERE mint = 'GUARD_MINT_65'",
    "DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT_65'",
    "DELETE FROM meme_rule_set_param_history WHERE reason = 'T4.95 guard'",
)


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0065"))


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


def test_the_revision_lands_on_0064_and_fits_the_version_column() -> None:
    source = (REPO_ROOT / "infra" / "migrations" / "versions" / f"{REVISION}.py").read_text(
        encoding="utf-8"
    )
    assert f'revision: str = "{REVISION}"' in source
    assert f'down_revision: str | None = "{PREVIOUS}"' in source
    assert len(REVISION) <= 32
    assert PULLBACK_CONTROL_RULE_SET_ID == CONTROL, "the id the worker subtracts is 0065's own"


@pytest.mark.asyncio
async def test_the_control_is_the_arm_minus_the_pullback_and_nothing_else(
    engine: AsyncEngine,
) -> None:
    """The pairing EXP-M25 needs, as one assertion: the same document, the
    entry immediate."""
    async with engine.connect() as connection:
        seeded = await connection.scalar(
            text(
                "SELECT name || '/' || version || ':' || kind || ':' || exp_ref || ':' || status "
                "|| ':' || (params ->> 'clock') || ':' || code_ref "
                "|| ':' || (params ? 'entry_pullback_pct')::text "
                "|| ':' || (params ? 'entry_pullback_window_s')::text "
                "FROM meme_rule_sets WHERE id = :c"
            ),
            {"c": CONTROL},
        )
        same = await connection.scalar(
            text(
                "SELECT (c.params = a.params - CAST(:keys AS text[]))::text "
                "FROM meme_rule_sets c, meme_rule_sets a WHERE c.id = :c AND a.id = :a"
            ),
            {"keys": list(PULLBACK_KEYS), "c": CONTROL, "a": ARM},
        )
    assert seeded == (
        "recuo_ctrl_v1/1:research_only:EXP-M25:active:15s:"
        "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit:false:false"
    )
    assert same == "true"


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
    control, arm = await _spec(engine, CONTROL), await _spec(engine, ARM)
    assert (control.kind, control.clock, control.exp_ref) == ("research_only", "15s", "EXP-M25")
    assert control.entry_pullback is None, "the control enters at t0"
    assert arm.entry_pullback is not None, "the arm still waits"
    assert replace(control.gate, description=arm.gate.description) == arm.gate
    assert (control.size_sol, control.max_sol_per_bet, control.max_exposure_per_mint_sol) == (
        arm.size_sol,
        arm.max_sol_per_bet,
        arm.max_exposure_per_mint_sol,
    )
    assert (control.max_open_positions, control.wallet_max_sol, control.daily_loss_cap_sol) == (
        arm.max_open_positions,
        arm.wallet_max_sol,
        arm.daily_loss_cap_sol,
    )
    mine, theirs = effective_params(control, {}), effective_params(arm, {})
    assert not isinstance(mine, str) and not isinstance(theirs, str)
    assert mine.exit_rules() == theirs.exit_rules(), "the same exit, counted from the entry"
    async with AsyncSession(engine) as session:
        labels = {s.label for s in await load_active_rule_sets(session)}
    assert {"recuo_ctrl_v1/1", "recuo_v1/1", "operator/5", "operator/6"} <= labels


@pytest.mark.asyncio
async def test_the_executors_own_query_never_selects_the_control(upgraded: str) -> None:
    """Paper by construction: ``auto_approve.operator_proposals`` — the live
    executor's selection — run on a ``proposed`` paper proposal of each set."""
    now = datetime.now(UTC)
    ids = {
        "control": "00000000-0000-4000-8000-000000006501",
        "desk": "00000000-0000-4000-8000-000000006502",
    }
    await _write(
        upgraded,
        [
            (_PROPOSED, {"id": ids["control"], "rule_set": CONTROL, "at": now}),
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
    assert ids["control"] not in selected


@pytest.mark.asyncio
async def test_the_desk_and_the_arm_are_untouched(engine: AsyncEngine) -> None:
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
        waiting = [
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT name || '/' || version FROM meme_rule_sets "
                    "WHERE params ? 'entry_pullback_pct' OR params ? 'entry_pullback_window_s'"
                )
            )
        ]
    assert desk == ["operator/5", "operator/6"]
    assert waiting == ["recuo_v1/1"], "the arm keeps its cell and no other set waits"


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0065_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


def test_the_upgrade_refuses_without_an_active_arm(upgraded: str) -> None:
    config = alembic_config(upgraded)
    target: dict[str, object] = {"a": ARM}
    retire = (
        "UPDATE meme_rule_sets SET status = 'retired', retired_at = now() WHERE id = :a",
        target,
    )
    revive = (
        "UPDATE meme_rule_sets SET status = 'active', retired_at = NULL WHERE id = :a",
        target,
    )
    try:
        command.downgrade(config, PREVIOUS)
        asyncio.run(_write(upgraded, [retire]))
        with pytest.raises(DBAPIError, match="recuo_v1/1 is missing or not active"):
            command.upgrade(config, REVISION)
        assert _revision_of(upgraded) == PREVIOUS and _count_of(upgraded, CONTROL) == 0
    finally:
        asyncio.run(_write(upgraded, [revive]))
        command.upgrade(config, REVISION)
    assert _revision_of(upgraded) == REVISION and _count_of(upgraded, CONTROL) == 1


@pytest.mark.parametrize(
    "clock_sql",
    [
        'params || \'{"clock": "1m"}\'::jsonb',
        "params - 'clock'",
        "params || '{\"clock\": null}'::jsonb",
    ],
)
def test_the_upgrade_refuses_when_the_arm_is_not_on_the_15s_clock(
    upgraded: str, clock_sql: str
) -> None:
    """The control copies the arm's clock; anything but ``15s`` would plant a
    control the event lane never reads — no pair at ``t0``. Refused by name,
    nothing seeded, the revision stays ``0064``."""
    config = alembic_config(upgraded)
    target: dict[str, object] = {"a": ARM}
    saved = asyncio.run(
        _scalar(upgraded, "SELECT params::text FROM meme_rule_sets WHERE id = :a", a=ARM)
    )
    move = (f"UPDATE meme_rule_sets SET params = {clock_sql} WHERE id = :a", target)  # noqa: S608
    restore_params: dict[str, object] = {"a": ARM, "p": saved}
    restore = ("UPDATE meme_rule_sets SET params = CAST(:p AS jsonb) WHERE id = :a", restore_params)
    try:
        command.downgrade(config, PREVIOUS)
        asyncio.run(_write(upgraded, [move]))
        with pytest.raises(DBAPIError, match="recuo_v1/1 is not on the 15s clock"):
            command.upgrade(config, REVISION)
        assert _revision_of(upgraded) == PREVIOUS and _count_of(upgraded, CONTROL) == 0
    finally:
        asyncio.run(_write(upgraded, [restore]))
        command.upgrade(config, REVISION)
    assert _revision_of(upgraded) == REVISION and _count_of(upgraded, CONTROL) == 1


def test_the_downgrade_refuses_while_any_row_references_the_control(upgraded: str) -> None:
    config = alembic_config(upgraded)
    proposal = "00000000-0000-4000-8000-000000006511"
    bet = "00000000-0000-4000-8000-000000006512"
    change = "00000000-0000-4000-8000-000000006513"
    guarded: list[tuple[list[tuple[str, dict[str, object]]], str]] = [
        (
            [(_APPROVED, {"id": proposal, "rule_set": CONTROL})],
            "proposals reference the seeded recuo_ctrl_v1 set - they are EXP-M25's "
            "immediate-entry pairs and cannot be removed under them",
        ),
        (
            [
                (_APPROVED, {"id": proposal, "rule_set": OPERATOR_6}),
                (_A_BET, {"id": bet, "proposal": proposal, "rule_set": CONTROL}),
            ],
            "bets reference the seeded recuo_ctrl_v1 set",
        ),
        (
            [(_A_PARAM_CHANGE, {"id": change, "rule_set": CONTROL})],
            "param history rows reference the seeded recuo_ctrl_v1 set",
        ),
        (
            [(_A_REFUSAL, {"rule_set": CONTROL})],
            "refusal rows reference the seeded recuo_ctrl_v1 set",
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
        assert _count_of(upgraded, CONTROL) == 0 and _count_of(upgraded, ARM) == 1
    finally:
        command.upgrade(config, REVISION)
    assert _revision_of(upgraded) == REVISION and _count_of(upgraded, CONTROL) == 1
