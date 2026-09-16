"""T4.27 against a real Postgres at ``head`` — a bet on a **Mayhem** coin is
marked and sold by the vault (``real_sol_reserves``), never by the formula
over the agent's virtual SOL; the row says so; the gate refuses a Mayhem coin
by name on both clocks; the 15-second fold writes ``mcap_executable_sol``
beside the theoretical cap; the minute clock's flag read is one bounded
primary-key query.

KAT's numbers (15/09 17:37 BRT): ``virtual_sol_reserves`` 23,9 → 1 977 SOL in
60 s with 5 holders. Here the vault holds 0,9 SOL while the formula quotes a
sale of about 3,3 SOL for a 0,05 SOL stake.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_indicators.meme.fast import FastPoint
from hunter_meme_worker.features import CurveObservation, MinuteInputs, build_row
from hunter_meme_worker.features_fast import FastInputs, build_fast_row
from hunter_meme_worker.lab import LabContext, closed_minutes, lab_tick
from hunter_meme_worker.lab_repo_mayhem import mayhem_flags_for
from hunter_meme_worker.repo import insert_features, insert_snapshot, upsert_token
from hunter_meme_worker.repo_fast import insert_fast_rows, load_fast_points

from .test_lab_fast import FLOW_V2_ID, _fast_row  # pyright: ignore[reportPrivateUsage]
from .test_lab_persistence import (
    NOW,
    FakeQuotes,
    Heartbeats,
    _approve,  # pyright: ignore[reportPrivateUsage]
    _bet_of,  # pyright: ignore[reportPrivateUsage]
    _one,  # pyright: ignore[reportPrivateUsage]
    _rule_set,  # pyright: ignore[reportPrivateUsage]
    _snapshot,  # pyright: ignore[reportPrivateUsage]
    _token,  # pyright: ignore[reportPrivateUsage]
    lab,
)

__all__ = ["lab"]  # the fixture travels with its module

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
CREATED = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


async def _plant_mayhem(
    factory: async_sessionmaker[AsyncSession], mint: str, *, created_at: datetime
) -> None:
    async with role_session(factory, db_role=WORKER) as session:
        await upsert_token(
            session,
            replace(
                _token(mint, created_at=created_at), mayhem_enabled=True, mayhem_state="active"
            ),
        )


def _pushed(mint: str, at: datetime) -> object:
    """The agent's push: 1 977 SOL of virtual reserve, the vault at 0,9 SOL."""
    return replace(
        _snapshot(mint, at, "1977", "900000000"),
        source="solana_rpc",
        real_sol_reserves=Decimal("0.9"),
        mayhem_enabled=True,
    )


async def test_a_mayhem_bet_is_marked_and_sold_by_the_vault_and_the_row_says_so(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    rule_set = await _rule_set(db_engine, f"mayhem_{uuid4().hex[:6]}")
    mint = f"MAYH_{uuid4().hex[:8]}"
    decided = NOW - timedelta(seconds=60)
    entry_at = decided + timedelta(seconds=30)
    await _plant_mayhem(db_session_factory, mint, created_at=decided - timedelta(minutes=2))
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(
            session, replace(_snapshot(mint, entry_at, "32.4", "993000000"), mayhem_enabled=True)
        )
    proposal = await _approve(
        db_session_factory, mint=mint, rule_set_id=rule_set, decided_at=decided
    )
    assert (await lab_tick(ctx, now=NOW)).fills.filled == 1
    opened = await _bet_of(db_session_factory, proposal)
    assert opened["status"] == "open" and opened["mark_sol"] < Decimal("0.05")

    trigger = entry_at + timedelta(seconds=60)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _pushed(mint, trigger))  # type: ignore[arg-type]
    await lab_tick(ctx, now=trigger + timedelta(seconds=5))
    pending = await _bet_of(db_session_factory, proposal)
    assert pending["status"] == "open" and pending["exit_intent"]["reason"] == "target"
    assert pending["mark_sol"] == Decimal("0.8842500000"), "0,9 SOL of vault minus the 1,75 % fee"
    assert pending["mark_sol"] < Decimal(3), "the formula would have said ~3,3 SOL"

    sale_at = trigger + timedelta(seconds=30)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _pushed(mint, sale_at))  # type: ignore[arg-type]
    await lab_tick(ctx, now=sale_at + timedelta(seconds=5))
    closed = await _bet_of(db_session_factory, proposal)
    assert closed["status"] == "closed" and closed["exit"]["reason"] == "target"
    assert closed["exit"]["real_sol_cap_applied"] is True
    assert closed["exit"]["mark_basis"] == "real_sol_reserves"
    assert closed["exit"]["curve_proceeds_sol"] == "0.9"
    assert closed["exit"]["sol_received"] == "0.88425"
    assert closed["exit"]["snapshot"]["mayhem_enabled"] is True
    assert closed["pnl_sol"] == Decimal("0.88425") - closed["initial_risk_sol"]
    assert closed["outcome_quality"] == "measured", "a capped sale is a measured one"


async def test_the_minute_gate_refuses_a_mayhem_coin_by_name_and_reads_its_flag_bounded(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx, _quotes, beats = lab
    mint = f"MAYG_{uuid4().hex[:8]}"
    closed = NOW.replace(second=0, microsecond=0) - timedelta(minutes=1)
    observed = closed - timedelta(seconds=20)
    await _plant_mayhem(db_session_factory, mint, created_at=closed - timedelta(seconds=120))
    row = build_row(
        MinuteInputs(
            mint=mint,
            end_time=closed,
            created_at=closed - timedelta(seconds=120),
            initial_real_token_reserves=Decimal("793100000"),
            snapshot=CurveObservation(
                observed_at=observed,
                source="solana_rpc",
                real_token_reserves=Decimal("620100000"),
                mcap_sol=Decimal("1981"),
                complete=False,
                real_sol_reserves=Decimal("0.9"),
                mayhem_enabled=True,
            ),
        )
    )
    assert row.mcap_executable_sol == Decimal("0.9000000000")
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_features(session, [row])
        flags = await mayhem_flags_for(session, [mint, "NOPE_MINT"])
        (plan,) = (
            (
                await session.execute(
                    text(
                        "EXPLAIN (FORMAT TEXT) SELECT mint, mayhem_enabled, mayhem_state "
                        "FROM meme_tokens WHERE mint = ANY(:mints)"
                    ),
                    {"mints": [mint]},
                )
            )
            .scalars()
            .all()[:1]
        )
    assert flags == {mint: (True, "active")}, "one bounded read; an absent mint stays unknown"
    assert "meme_tokens" in plan
    assert closed_minutes(ctx.state, NOW, backlog=3)[-1] == closed
    report = await lab_tick(ctx, now=NOW)
    assert report.minute == closed and report.rows_evaluated >= 1
    refusals = ctx.state.refusals["meme_paper_v0"]
    assert refusals["mayhem_curve"] >= 1, refusals
    assert "mayhem_curve" in beats.written[-1]["lab_gate_refusals"]
    async with role_session(db_session_factory, db_role=WORKER) as session:
        proposed = await session.scalar(
            text("SELECT count(*) FROM meme_proposals WHERE mint = :mint"), {"mint": mint}
        )
        written = await session.scalar(
            text(
                "SELECT mcap_executable_sol FROM meme_features_1m "
                "WHERE mint = :mint AND end_time = :minute"
            ),
            {"mint": mint, "minute": closed},
        )
    assert proposed == 0
    assert written is not None and written <= Decimal(1), (
        "the minute INSERT carries mcap_executable_sol since the merge of T4.26 + T4.27: "
        "in a Mayhem coin it is capped by the real SOL in the curve (0,9 SOL in this fixture)"
    )


async def test_the_15s_gate_refuses_a_mayhem_coin_and_the_fast_fold_writes_the_cap(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx, _quotes, _beats = lab
    mint = f"MAYF_{uuid4().hex[:8]}"
    await _plant_mayhem(db_session_factory, mint, created_at=CREATED)
    photo = CREATED + timedelta(seconds=120)
    as_of = photo + timedelta(seconds=2)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _pushed(mint, photo))  # type: ignore[arg-type]
        points = await load_fast_points(session, mints=[mint], as_of=as_of)
    (point,) = points.points[mint]
    assert isinstance(point, FastPoint)
    assert point.real_sol_reserves == Decimal("0.9") and point.mayhem_enabled is True
    fast = build_fast_row(
        FastInputs(
            mint=mint,
            as_of=as_of,
            created_at=CREATED,
            initial_real_token_reserves=Decimal("793100000"),
            points=points.points[mint],
            snapshot_source=points.newest_source[mint],
            mayhem_state="active",
        )
    )
    assert fast.mcap_executable_sol == Decimal("0.9000000000")
    assert fast.mcap_sol is not None and fast.mcap_sol > Decimal(2000)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_fast_rows(
            session, [fast, _fast_row(mint, as_of + timedelta(seconds=15), photo)]
        )
    stored = await _one(
        db_session_factory,
        "SELECT mcap_sol, mcap_executable_sol FROM meme_features_15s "
        "WHERE mint = :mint AND as_of = :as_of",
        mint=mint,
        as_of=as_of,
    )
    assert stored["mcap_executable_sol"] == Decimal("0.9000000000")
    assert stored["mcap_sol"] == fast.mcap_sol
    report = await lab_tick(ctx, now=as_of + timedelta(seconds=20))
    assert report.proposals == 0
    async with role_session(db_session_factory, db_role=WORKER) as session:
        name = await session.scalar(
            text("SELECT name FROM meme_rule_sets WHERE id = CAST(:id AS uuid)"), {"id": FLOW_V2_ID}
        )
    refusals = ctx.state.refusals[str(name)]
    assert refusals["mayhem_curve"] >= 1, refusals
