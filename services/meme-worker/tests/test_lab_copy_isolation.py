"""H-037 task I (EXP-M28): the Lab must not touch the copy lane's rows.

The copy lane (``copy_lane*.py``) writes ``meme_proposals`` born ``approved``/``paper`` and
``meme_paper_bets`` under rule sets whose ``params.clock = 'copy'``, and it prices, marks and
sells them with its own latency model. The Lab used to read **every** ``approved`` proposal and
**every** ``open`` bet, so a copy proposal would have been marked ``unfilled/rule_set_inactive``
and a copy bet sold on the next 15-second photo without the lane's latency. These tests run the
real ``lab_tick`` against a real Postgres: a rule set is flipped to ``clock = 'copy'`` *after*
its rows exist (the same row shapes the Lab writes), and the Lab must leave them alone while a
twin set on the ordinary clock, in the very same tick, is still served (the control).

Each test plants its own rule sets, as ``test_lab_persistence`` does, and an autouse fixture
closes every bet they leave open: the database is shared by the module, and a leftover open
bet of the Lab changes the ``closed == 1`` counts of the tests that run after this one.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_worker import lab_repo, lab_repo_bets
from hunter_meme_worker.copy_spec import COPY_CLOCK
from hunter_meme_worker.lab import LabContext, lab_tick
from hunter_meme_worker.lab_repo import load_active_rule_sets
from hunter_meme_worker.lab_repo_bets import count_indeterminate, load_open_bets
from hunter_meme_worker.repo import insert_snapshot

from .test_lab_persistence import (
    APP,
    NOW,
    WORKER,
    FakeQuotes,
    Heartbeats,
    _approve,  # pyright: ignore[reportPrivateUsage]
    _bet_of,  # pyright: ignore[reportPrivateUsage]
    _one,  # pyright: ignore[reportPrivateUsage]
    _open_bet,  # pyright: ignore[reportPrivateUsage]
    _plant_curve,  # pyright: ignore[reportPrivateUsage]
    _rule_set,  # pyright: ignore[reportPrivateUsage]
    _snapshot,  # pyright: ignore[reportPrivateUsage]
    lab,
)
from .test_rule_set_loading import _failed  # pyright: ignore[reportPrivateUsage]

__all__ = ["lab"]  # the fixture travels with its module

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

_MY_SETS = "^(copyp|ctrlp|copyb|ctrlb|cindet|copyc|copyl|launchp)_"


@pytest_asyncio.fixture(autouse=True)
async def leave_no_open_bet(db_engine: AsyncEngine) -> AsyncIterator[None]:
    yield
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_paper_bets b SET status = 'closed', "
                "  exit_at = b.entry_at + interval '1 minute', exit = '{}'::jsonb, "
                "  pnl_sol = 0, r_multiple = 0 "
                "FROM meme_rule_sets rs WHERE rs.id = b.rule_set_id AND b.status = 'open' "
                "  AND rs.name ~ :names"
            ),
            {"names": _MY_SETS},
        )


async def _set_clock(engine: AsyncEngine, rule_set_id: str, clock: str) -> None:
    """Owner write: the ``params.clock`` that tells which lane a set belongs to."""
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_rule_sets SET params = params || CAST(:clock AS jsonb) "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"id": rule_set_id, "clock": f'{{"clock": "{clock}"}}'},
        )


async def _make_copy(engine: AsyncEngine, rule_set_id: str) -> None:
    """What ``copy_v0/1`` carries and an ordinary set does not: ``params.clock = 'copy'``."""
    await _set_clock(engine, rule_set_id, COPY_CLOCK)


async def _rule_set_id_of_bet(factory: async_sessionmaker[AsyncSession], proposal: str) -> str:
    return str((await _bet_of(factory, proposal))["rule_set_id"])


async def test_the_lab_leaves_an_approved_copy_proposal_to_the_copy_lane(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    decided = NOW - timedelta(seconds=60)
    entry_at = decided + timedelta(seconds=30)
    rows: dict[str, tuple[str, str]] = {}
    for label in ("copyp", "ctrlp"):
        rule_set = await _rule_set(db_engine, f"{label}_{uuid4().hex[:6]}")
        mint = f"{label.upper()}_{uuid4().hex[:8]}"
        await _plant_curve(
            db_session_factory,
            mint,
            [
                (entry_at, "32.4", "993000000")
            ],  # a photo after the decision: the Lab *could* fill it
            created_at=decided - timedelta(minutes=2),
        )
        proposal = await _approve(
            db_session_factory, mint=mint, rule_set_id=rule_set, decided_at=decided
        )
        rows[label] = (rule_set, proposal)
    await _make_copy(db_engine, rows["copyp"][0])

    tick = await lab_tick(ctx, now=NOW)

    assert tick.fills.filled >= 1, "the control: an ordinary approved proposal is still filled"
    control = await _bet_of(db_session_factory, rows["ctrlp"][1])
    assert control["proposal_status"] == "filled"
    copied = await _bet_of(db_session_factory, rows["copyp"][1])
    assert copied["proposal_status"] == "approved", (
        "the copy lane's own, still waiting for its price"
    )
    assert copied["refusal"] is None and copied["id"] is None, "no unfill, no Lab bet"


async def _two_open_bets(
    ctx: LabContext,
    factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
) -> tuple[tuple[str, str], tuple[str, str]]:
    """``(copy, control)`` as ``(mint, proposal)``: two bets the Lab opened, one set then made a copy set."""
    copy_mint, copy_proposal, _ = await _open_bet(ctx, factory, engine, "copyb")
    control_mint, control_proposal, _ = await _open_bet(ctx, factory, engine, "ctrlb")
    await _make_copy(engine, await _rule_set_id_of_bet(factory, copy_proposal))
    return (copy_mint, copy_proposal), (control_mint, control_proposal)


async def test_the_lab_neither_marks_nor_sells_an_open_copy_bet(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    (copy_mint, copy_proposal), (control_mint, control_proposal) = await _two_open_bets(
        ctx, db_session_factory, db_engine
    )
    before = await _bet_of(db_session_factory, copy_proposal)
    trigger = before["entry_at"] + timedelta(seconds=60)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        for mint in (
            copy_mint,
            control_mint,
        ):  # 4x on both: the target fires on any bet the Lab owns
            await insert_snapshot(session, _snapshot(mint, trigger, "70", "460000000"))

    await lab_tick(ctx, now=trigger + timedelta(seconds=5))

    control = await _bet_of(db_session_factory, control_proposal)
    assert control["exit_intent"]["reason"] == "target", "the control: the Lab owns this one"
    after = await _bet_of(db_session_factory, copy_proposal)
    assert after["status"] == "open"
    assert after["exit_intent"] is None, "no exit decided by the Lab on a copy bet"
    assert after["mark_at"] == before["mark_at"] and after["mark_sol"] == before["mark_sol"]
    assert after["high_water_x"] == before["high_water_x"]


async def test_the_lab_read_of_open_bets_hides_the_copy_lane_bets(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    (_cm, copy_proposal), (_km, control_proposal) = await _two_open_bets(
        ctx, db_session_factory, db_engine
    )
    copy_bet = str((await _bet_of(db_session_factory, copy_proposal))["id"])
    control_bet = str((await _bet_of(db_session_factory, control_proposal))["id"])

    async with role_session(db_session_factory, db_role=WORKER) as session:
        lab_view = {b.state.id for b in await load_open_bets(session)}

    assert control_bet in lab_view and copy_bet not in lab_view


async def test_an_operator_cancel_does_not_reject_a_copy_proposal(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    """A ``rejected`` copy row is read back on restart as "not admitted" and would free its
    (stratum, mint) key: the lane's funnel is not the operator's to edit."""
    ctx, _quotes, _beats = lab
    rule_set = await _rule_set(db_engine, f"copyc_{uuid4().hex[:6]}")
    await _make_copy(db_engine, rule_set)
    proposal = await _approve(
        db_session_factory,
        mint=f"COPYC_{uuid4().hex[:8]}",
        rule_set_id=rule_set,
        decided_at=NOW - timedelta(seconds=10),
    )
    command_id = str(uuid4())
    async with role_session(db_session_factory, db_role=APP) as session:
        await session.execute(
            text(
                "INSERT INTO meme_operator_commands (id, proposal_id, command, issued_by, issued_at) "
                "VALUES (:id, :proposal, 'cancel', 'user_test', :at)"
            ),
            {"id": command_id, "proposal": proposal, "at": NOW - timedelta(seconds=5)},
        )

    await lab_tick(ctx, now=NOW)

    assert (await _bet_of(db_session_factory, proposal))["proposal_status"] == "approved"
    answer = await _one(
        db_session_factory, "SELECT result FROM meme_operator_commands WHERE id = :c", c=command_id
    )
    assert answer["result"]["status"] == "refused", "answered by name, never applied"


async def test_the_lab_indeterminate_counter_does_not_count_copy_censorships(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    _mint, proposal, _entry = await _open_bet(ctx, db_session_factory, db_engine, "cindet")
    bet = await _bet_of(db_session_factory, proposal)
    async with db_engine.begin() as connection:  # the copy lane's censoring: closed, indeterminate
        await connection.execute(
            text(
                "UPDATE meme_paper_bets SET status = 'closed', exit_at = entry_at + interval '1 minute', "
                "  exit = '{}'::jsonb, pnl_sol = 0, r_multiple = 0, "
                "  outcome_quality = 'indeterminate', outcome_quality_reason = 'leader_gap', "
                "  outcome_quality_at = entry_at + interval '1 minute' WHERE id = :id"
            ),
            {"id": bet["id"]},
        )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        with_lab_set = await count_indeterminate(session)
    await _make_copy(db_engine, str(bet["rule_set_id"]))
    async with role_session(db_session_factory, db_role=WORKER) as session:
        with_copy_set = await count_indeterminate(session)

    assert with_copy_set == with_lab_set - 1


async def test_the_lab_loader_skips_a_copy_set_without_calling_it_a_load_failure(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    """``clock = 'copy'`` is not in ``CLOCKS``: the loader would log an error and count a
    ``meme_rule_set_load_failed`` on every tick for the set the copy lane loads itself."""
    name = f"copyl_{uuid4().hex[:6]}"
    rule_set = await _rule_set(db_engine, name)
    await _make_copy(db_engine, rule_set)
    before = _failed(f"{name}/1")

    async with role_session(db_session_factory, db_role=WORKER) as session:
        loaded = {spec.id for spec in await load_active_rule_sets(session)}

    assert rule_set not in loaded
    assert _failed(f"{name}/1") == before, "an excluded set is not a parse failure"


def test_the_lab_exclusion_is_the_copy_lane_marker() -> None:
    """If the lane renames its ``params.clock``, the Lab's five statements must follow."""
    for statement in (
        lab_repo._RULE_SETS,  # pyright: ignore[reportPrivateUsage]
        lab_repo._APPROVED,  # pyright: ignore[reportPrivateUsage]
        lab_repo._CANCEL,  # pyright: ignore[reportPrivateUsage]
        lab_repo_bets._OPEN_BETS,  # pyright: ignore[reportPrivateUsage]
        lab_repo_bets._INDETERMINATE,  # pyright: ignore[reportPrivateUsage]
    ):
        assert f"'{COPY_CLOCK}'" in str(statement)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "KNOWN, NOT FIXED BY TASK I (reported to the orchestrator): launch_v0 (clock='event') "
        "proposals are born 'approved' and the Lab - whose loader skips event sets - marks them "
        "unfilled/rule_set_inactive if its tick lands before launch_lane_bets.mark_filled"
    ),
)
async def test_the_lab_leaves_an_approved_launch_lane_proposal_alone(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    """The side finding of H-037 task I, as an executable statement of what is wrong today.
    When the launch lane's ownership is fixed this test XPASSes and strict mode forces the
    marker to be removed."""
    ctx, _quotes, _beats = lab
    rule_set = await _rule_set(db_engine, f"launchp_{uuid4().hex[:6]}")
    await _set_clock(db_engine, rule_set, "event")
    proposal = await _approve(
        db_session_factory,
        mint=f"LAUNCHP_{uuid4().hex[:8]}",
        rule_set_id=rule_set,
        decided_at=NOW - timedelta(seconds=1),
    )

    await lab_tick(ctx, now=NOW)

    assert (await _bet_of(db_session_factory, proposal))["proposal_status"] == "approved"
