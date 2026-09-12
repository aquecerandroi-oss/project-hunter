# pyright: reportPrivateUsage=false
"""T4.11 against a real Postgres at ``head`` — one file, one container.

What only a database can prove: the ``0029`` seed parses into the two moonshot
arms and ``operator/2`` (``operator/1`` gone from the active set); a moonshot
bet filled on the curve **holds through the migration** and is marked by the
PumpSwap pool's tape (``mark_source = 'pool_tape'``, ``mark_stale_s``), the
target firing on one pool trade and the sale priced on the **next** one — with
the impact of the participation and the fee of the band of that price; a
trade the tape delivers *after* the tick cannot fill it (the look-ahead test
against Postgres); and a pool that goes silent with the mark at half the cost
is closed ``dead`` at zero when the window finds no trade to sell into.

Run alone (``timeout 590``): it shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_indicators.meme.pool import quote_pool_sell
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.lab import LabContext, LabState, lab_tick
from hunter_meme_worker.lab_repo import load_active_rule_sets
from hunter_meme_worker.repo_tape import TradeRow, insert_trades

from .test_lab_persistence import (  # pyright: ignore[reportPrivateUsage]
    FakeQuotes,
    Heartbeats,
    _approve,
    _bet_of,
    _plant_curve,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
MOONSHOT_10X_ID = "01994d00-6c1a-7000-8000-000000000005"
MOONSHOT_25X_ID = "01994d00-6c1a-7000-8000-000000000006"
OPERATOR_2_ID = "01994d00-6c1a-7000-8000-000000000007"
CREATED = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
"""A Brasília morning (09:00 BRT) inside the 2026-10 partitions."""
SUPPLY = Decimal(1_000_000_000)
LAMPORTS = 1_000_000_000
DECISION: dict[str, Any] = {
    "size_sol": "0.02",
    "target_x": "10",
    "trailing_pct": "50",
    "max_hold_s": 7200,
}


@pytest_asyncio.fixture
async def lab(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[LabContext]:
    yield LabContext(
        config=MemeConfig(enabled=True, lab_enabled=True),
        session_factory=db_session_factory,
        state=LabState(),
        quotes=FakeQuotes(),
        heartbeat=Heartbeats(),
    )


async def _moonshot_set(engine: AsyncEngine) -> str:
    """A rule set of this test's own, copying the 10× arm's frozen params (owner write)."""
    rule_set_id = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref) "
                "SELECT :id, :name, '1', 'research_only', params, code_ref, 'EXP-M4' "
                "FROM meme_rule_sets WHERE id = :seed"
            ),
            {
                "id": rule_set_id,
                "name": f"moonshot_test_{uuid4().hex[:8]}",
                "seed": MOONSHOT_10X_ID,
            },
        )
    return rule_set_id


async def _migrate(engine: AsyncEngine, mint: str, at: datetime) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_tokens SET migrated_at = :at, migrated_pool = 'POOL_TEST' "
                "WHERE mint = :mint"
            ),
            {"at": at, "mint": mint},
        )


def _pool_trade(
    mint: str, at: datetime, *, sol: str, tokens: str, received_at: datetime | None = None
) -> TradeRow:
    return TradeRow(
        block_time=at,
        signature=f"SIG_{uuid4().hex}",
        event_index=0,
        mint=mint,
        slot=446390104,
        received_at=received_at or at + timedelta(seconds=1),
        trader="POOL_TRADER",
        side="buy",
        sol_lamports=int(Decimal(sol) * LAMPORTS),
        token_amount=Decimal(tokens),
        price=Decimal(sol) / Decimal(tokens),
        program="pump_amm",
    )


async def _tape(factory: async_sessionmaker[AsyncSession], rows: list[TradeRow]) -> None:
    async with role_session(factory, db_role=WORKER) as session:
        await insert_trades(session, rows)


async def _open_moonshot(
    lab: LabContext,
    factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    mint: str,
    *,
    decided_at: datetime,
) -> tuple[str, Any]:
    """A moonshot bet filled on the curve: the proposal, then its open row."""
    rule_set_id = await _moonshot_set(engine)
    fill_at = decided_at + timedelta(seconds=10)
    await _plant_curve(factory, mint, [(fill_at, "34", "946000000")], created_at=CREATED)
    proposal_id = await _approve(
        factory, mint=mint, rule_set_id=rule_set_id, decided_at=decided_at, decision=DECISION
    )
    report = await lab_tick(lab, now=decided_at + timedelta(seconds=20))
    assert report.fills.filled >= 1
    row = await _bet_of(factory, proposal_id)
    assert row["status"] == "open" and row["entry_at"] == fill_at
    assert row["mark_source"] == "curve" and row["mark_stale_s"] is None
    assert row["params"]["exit_on_migration"] is False and row["params"]["trailing_arm_x"] == "3"
    assert row["params"]["exit_on_dead"] is True and row["params"]["max_hold_s"] == 7200
    return proposal_id, row


# ---- the seed ---------------------------------------------------------------------------


async def test_the_seed_plants_the_two_arms_and_operator_2_and_retires_operator_1(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with role_session(db_session_factory, db_role=WORKER) as session:
        specs = {s.label: s for s in await load_active_rule_sets(session)}
    assert "operator/1" not in specs, "retired by 0029"
    ten, twenty_five, operator = specs["moonshot_v0/1"], specs["moonshot_v0/2"], specs["operator/2"]
    for arm in (ten, twenty_five):
        assert arm.exp_ref == "EXP-M4" and arm.kind == "research_only"
        assert arm.exit_on_migration is False and arm.trailing_arm_x == Decimal(3)
        assert arm.exit_on_dead and (arm.dead_stale_s, arm.dead_mark_pct) == (900, Decimal(50))
        assert (arm.size_sol, arm.trailing_pct, arm.max_hold_s) == (
            Decimal("0.02"),
            Decimal(50),
            7200,
        )
        assert arm.max_loss_pct == Decimal(100) and arm.max_open_positions == 8
        assert arm.daily_loss_cap_sol == Decimal("0.20") and arm.max_sol_per_bet == Decimal("0.02")
        assert arm.gate.key == "sonda_de_hype" and arm.gate.min_hype_score == Decimal("0.6")
        assert (arm.gate.min_age_s, arm.gate.max_age_s, arm.gate.max_snipers) == (30, 300, 2)
        assert not arm.scales
    assert (ten.target_x, twenty_five.target_x) == (Decimal(10), Decimal(25))
    assert (ten.id, twenty_five.id, operator.id) == (
        MOONSHOT_10X_ID,
        MOONSHOT_25X_ID,
        OPERATOR_2_ID,
    )
    assert operator.kind == "operator" and operator.exp_ref is None
    assert operator.suggested() == {
        "size_sol": "0.05",
        "target_x": "10",
        "trailing_pct": "50",
        "max_hold_s": 7200,
        "exit_on_migration": False,
        "trailing_arm_x": "3",
        "exit_on_dead": True,
    }
    assert operator.gate.key == "comprar_cedo_na_curva" and operator.max_sol_per_bet == Decimal(
        "0.05"
    )


# ---- holding through the migration, the target on the pool, the look-ahead ------------


async def test_a_moonshot_holds_through_the_migration_and_sells_the_target_on_the_next_pool_trade(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    mint = f"MOON_{uuid4().hex[:8]}"
    decided = CREATED + timedelta(minutes=2)
    proposal_id, opened = await _open_moonshot(
        lab, db_session_factory, db_engine, mint, decided_at=decided
    )
    tokens = Decimal(opened["entry"]["tokens"])
    migrated = opened["entry_at"] + timedelta(seconds=60)
    await _migrate(db_engine, mint, migrated)
    first = migrated + timedelta(seconds=60)  # price 5e-7 → mcap 500 SOL, ~13× the cost: target
    late = migrated + timedelta(seconds=80)  # price 6e-7 — but the tape delivers it only at +95 s
    tick_2 = migrated + timedelta(seconds=90)
    await _tape(
        db_session_factory,
        [
            _pool_trade(mint, first, sol="0.5", tokens="1000000"),
            _pool_trade(
                mint,
                late,
                sol="0.6",
                tokens="1000000",
                received_at=migrated + timedelta(seconds=95),
            ),
        ],
    )

    report = await lab_tick(lab, now=tick_2)
    assert report.bets.marked >= 1 and report.bets.closed == 0
    row = await _bet_of(db_session_factory, proposal_id)
    assert row["status"] == "open", "the late trade does not exist for this tick"
    assert row["mark_source"] == "pool_tape" and row["mark_at"] == first
    assert row["mark_stale_s"] == 30, "90 s after the migration, 30 s after the last trade"
    expected_mark = quote_pool_sell(
        tokens,
        Decimal("0.0000005"),
        volume_5m_sol=Decimal("0.5"),
        total_supply=SUPPLY,
        path_fee_pct=Decimal("0.5"),
    )
    assert Decimal(row["mark_sol"]) == expected_mark.net_sol.quantize(Decimal("0.0000000001"))
    assert expected_mark.net_sol >= Decimal("0.2"), "≥ 10× of the 0,02 spent: the target"
    intent = row["exit_intent"]
    assert intent["reason"] == "target" and intent["venue"] == "pump_amm"
    assert intent["decided_at"] == first.isoformat() == intent["trade_block_time"]

    report = await lab_tick(lab, now=migrated + timedelta(seconds=150))
    assert report.bets.closed == 1
    row = await _bet_of(db_session_factory, proposal_id)
    assert row["status"] == "closed" and row["proposal_status"] == "filled"
    sale = quote_pool_sell(
        tokens,
        Decimal("0.0000006"),
        volume_5m_sol=Decimal("1.1"),
        total_supply=SUPPLY,
        path_fee_pct=Decimal("0.5"),
    )
    exit_ = row["exit"]
    assert exit_["reason"] == "target" and exit_["fill"] == "next_trade"
    assert row["exit_at"] == late and exit_["trade"]["block_time"] == late.isoformat()
    assert exit_["intent_trade_at"] == first.isoformat() and exit_["trigger"] == "rules"
    assert Decimal(exit_["sol_received"]) == sale.net_sol
    assert (exit_["tier_fee_pct"], exit_["path_fee_pct"]) == ("1.2", "0.5"), "mcap 600 SOL"
    assert exit_["impact_pct"] == "1", "0,33 SOL of 1,1 SOL in five minutes: capped at 1 %"
    assert exit_["mark_source"] == "pool_tape" and row["mark_source"] == "pool_tape"
    assert Decimal(row["pnl_sol"]) == (sale.net_sol - Decimal("0.02")).quantize(
        Decimal("0.0000000001")
    )
    assert Decimal(row["r_multiple"]) > 10


# ---- the pool goes silent: stale marks, then dead at zero --------------------------------


async def test_a_silent_pool_with_the_mark_at_half_the_cost_is_closed_dead_at_zero(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    mint = f"DEAD_{uuid4().hex[:8]}"
    decided = CREATED + timedelta(minutes=2)
    proposal_id, opened = await _open_moonshot(
        lab, db_session_factory, db_engine, mint, decided_at=decided
    )
    migrated = opened["entry_at"] + timedelta(seconds=60)
    await _migrate(db_engine, mint, migrated)
    only = migrated + timedelta(seconds=60)  # price 5e-9: the mark falls to ~1/7 of the cost
    await _tape(db_session_factory, [_pool_trade(mint, only, sol="0.005", tokens="1000000")])

    await lab_tick(lab, now=only + timedelta(seconds=30))
    row = await _bet_of(db_session_factory, proposal_id)
    assert row["status"] == "open" and row["exit_intent"] is None, "quiet is not dead"
    assert row["mark_source"] == "pool_tape" and row["mark_stale_s"] == 30
    assert Decimal(row["mark_sol"]) < Decimal("0.01")
    last_mark = row["mark_sol"]

    fired = only + timedelta(seconds=900)
    await lab_tick(lab, now=fired)
    row = await _bet_of(db_session_factory, proposal_id)
    assert row["status"] == "open" and row["mark_stale_s"] == 900
    assert row["exit_intent"]["reason"] == "dead"
    assert row["exit_intent"]["decided_at"] == fired.isoformat()
    assert row["exit_intent"]["trade_block_time"] is None, "fired by the tick, not by a trade"

    await lab_tick(lab, now=fired + timedelta(seconds=179))
    row = await _bet_of(db_session_factory, proposal_id)
    assert row["status"] == "open", "the window is 180 s; the tape may still print"

    report = await lab_tick(lab, now=fired + timedelta(seconds=180))
    assert report.bets.closed == 1
    row = await _bet_of(db_session_factory, proposal_id)
    exit_ = row["exit"]
    assert row["status"] == "closed" and exit_["reason"] == "dead" and exit_["fill"] == "none"
    assert exit_["sol_received"] == "0" and exit_["last_trade_at"] == only.isoformat()
    assert exit_["mark_stale_s"] == 1080 and Decimal(exit_["last_mark_sol"]) == Decimal(last_mark)
    assert Decimal(row["pnl_sol"]) == Decimal("-0.02") and Decimal(row["r_multiple"]) == -1
    assert row["mark_source"] == "pool_tape" and row["mark_stale_s"] is None
