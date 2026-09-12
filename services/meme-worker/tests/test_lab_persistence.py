"""The Lab loop against a real Postgres at ``head`` — one file, one container.

Everything proved here only exists in a database: the seed ``0022`` plants, the
gate counting today's refusals over real ``meme_features_1m`` rows, a proposal
filled on the **first** snapshot after its decision (and the leakage test: the
future is rewritten and the entry does not move), the exits by target, time
stop, migration and ``sell_now`` each priced on the snapshot *after* the rule
fired, the named ``unfilled`` refusals including the daily loss cap, the
``rug_no_snapshot`` close, the two views, and the grants as the roles.

Every test plants its **own** rule set (as the owner, the way the migration
does) so wallets, caps and open-position counts never bleed between tests.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
import pytest_asyncio
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.features import CurveObservation, MinuteInputs, build_row
from hunter_meme_worker.lab import LabContext, LabState, closed_minutes, lab_tick
from hunter_meme_worker.repo import (
    SnapshotRow,
    TokenRow,
    insert_features,
    insert_snapshot,
    upsert_token,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from hunter_core.db.session import role_session
from hunter_exchanges.pumpfun.models import NormalizedSolPrice

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
APP = "hunter_app"
RESEARCH_ID = "01994d00-6c1a-7000-8000-000000000001"
OPERATOR_ID = "01994d00-6c1a-7000-8000-000000000002"
NOW = datetime(2026, 10, 5, 12, 10, 30, tzinfo=UTC)
"""A Brasília afternoon (09:10 BRT) inside the 2026-10 partitions."""


class FakeQuotes:
    def __init__(self) -> None:
        self.calls = 0

    async def get_sol_price(self) -> NormalizedSolPrice:
        self.calls += 1
        return NormalizedSolPrice(
            price_usd=Decimal("101.4445"), as_of=NOW, stale=False, observed_at=NOW, received_at=NOW
        )


class Heartbeats:
    def __init__(self) -> None:
        self.written: list[dict[str, str]] = []

    async def __call__(self, mapping: dict[str, str]) -> None:
        self.written.append(mapping)


@pytest_asyncio.fixture
async def lab(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[tuple[LabContext, FakeQuotes, Heartbeats]]:
    quotes, beats = FakeQuotes(), Heartbeats()
    ctx = LabContext(
        config=MemeConfig(enabled=True, lab_enabled=True),
        session_factory=db_session_factory,
        state=LabState(),
        quotes=quotes,
        heartbeat=beats,
    )
    yield ctx, quotes, beats


async def _rule_set(engine: AsyncEngine, name: str, *, kind: str = "research_only") -> str:
    """A rule set of this test's own, copying the seed's frozen params (owner write)."""
    rule_set_id = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref) "
                "SELECT :id, :name, '1', :kind, params, code_ref, "
                "  CASE WHEN :kind = 'operator' THEN NULL ELSE 'EXP-M1' END "
                "FROM meme_rule_sets WHERE id = :seed"
            ),
            {"id": rule_set_id, "name": name, "kind": kind, "seed": RESEARCH_ID},
        )
    return rule_set_id


def _token(mint: str, *, created_at: datetime) -> TokenRow:
    return TokenRow(
        mint=mint,
        first_seen_source="pumpportal_ws",
        first_seen_at=created_at,
        last_seen_at=created_at,
        created_at=created_at,
        initial_real_token_reserves=Decimal("793100000"),
        # 0024 pairs the denominator with its source (T4.2d); a bare denominator
        # is refused by ``ck_meme_tokens_a_denominator_names_its_source``.
        progress_denominator_source="observed_virgin",
        total_supply=Decimal(1_000_000_000),
    )


def _snapshot(
    mint: str, at: datetime, sol: str, tokens: str, *, complete: bool = False
) -> SnapshotRow:
    return SnapshotRow(
        observed_at=at,
        mint=mint,
        source="pumpfun_rest",
        virtual_sol_reserves=Decimal(sol),
        virtual_token_reserves=Decimal(tokens),
        real_sol_reserves=Decimal(sol) - Decimal(30),
        real_token_reserves=Decimal(tokens) - Decimal("279900000"),
        total_supply=Decimal(1_000_000_000),
        complete=complete,
    )


async def _plant_curve(
    factory: async_sessionmaker[AsyncSession],
    mint: str,
    points: list[tuple[datetime, str, str]],
    *,
    created_at: datetime,
    complete_from: datetime | None = None,
) -> None:
    async with role_session(factory, db_role=WORKER) as session:
        await upsert_token(session, _token(mint, created_at=created_at))
        for at, sol, tokens in points:
            complete = complete_from is not None and at >= complete_from
            await insert_snapshot(session, _snapshot(mint, at, sol, tokens, complete=complete))


async def _approve(
    factory: async_sessionmaker[AsyncSession],
    *,
    mint: str,
    rule_set_id: str,
    decided_at: datetime,
    decision: dict[str, Any] | None = None,
) -> str:
    """What the desk writes: a manual proposal, already approved by a user."""
    proposal_id = str(uuid4())
    async with role_session(factory, db_role=APP) as session:
        await session.execute(
            text(
                "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
                "  expires_at, reasons, suggested, decision, decided_by, decided_at) "
                "VALUES (:id, :mint, :rule_set_id, 'operator', 'approved', :decided_at, "
                "  :expires_at, '[\"operator_manual\"]'::jsonb, '{}'::jsonb, "
                "  CAST(:decision AS jsonb), 'user_test', :decided_at)"
            ),
            {
                "id": proposal_id,
                "mint": mint,
                "rule_set_id": rule_set_id,
                "decided_at": decided_at,
                "expires_at": decided_at + timedelta(seconds=120),
                "decision": json.dumps(decision or {"size_sol": "0.05"}),
            },
        )
    return proposal_id


async def _one(factory: async_sessionmaker[AsyncSession], sql: str, **params: Any) -> Any:
    async with role_session(factory, db_role=WORKER) as session:
        return (await session.execute(text(sql), params)).mappings().one()


async def _bet_of(factory: async_sessionmaker[AsyncSession], proposal_id: str) -> Any:
    return await _one(
        factory,
        "SELECT b.*, p.status AS proposal_status, p.refusal FROM meme_proposals p "
        "LEFT JOIN meme_paper_bets b ON b.id = p.bet_id WHERE p.id = :id",
        id=proposal_id,
    )


# ---- seed and gate ------------------------------------------------------------------


async def test_the_seed_plants_the_two_rule_sets_the_contract_names(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with role_session(db_session_factory, db_role=APP) as session:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT id::text AS id, name, version, kind, exp_ref, status, params "
                        "FROM meme_rule_sets WHERE id IN (:a, :b) ORDER BY name"
                    ),
                    {"a": RESEARCH_ID, "b": OPERATOR_ID},
                )
            )
            .mappings()
            .all()
        )
    assert [(r["name"], r["version"], r["kind"], r["exp_ref"], r["status"]) for r in rows] == [
        ("meme_paper_v0", "1", "research_only", "EXP-M1", "active"),
        ("operator", "1", "operator", None, "active"),
    ]
    for row in rows:
        params = row["params"]
        assert (params["size_sol"], params["target_x"], params["trailing_pct"]) == (
            "0.05",
            "2",
            "30",
        )
        assert params["max_hold_s"] == 900
        assert (params["wallet_max_sol"], params["max_sol_per_bet"]) == ("2.0", "0.05")
        assert params["daily_loss_cap_sol"] == "0.20"
        assert (params["min_age_s"], params["max_age_s"]) == (30, 600)
        assert (params["min_progress_pct"], params["max_progress_pct"]) == ("2", "50")
        assert params["fee_pct"] == "1.75"


async def test_the_gate_reads_only_closed_minutes_and_counts_todays_refusals_by_name(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Real T4.2 rows (``creator_sold`` NULL with a reason, no volume) through the
    frozen EXP-M1 gate: nothing is proposed, and the heartbeat says why."""
    ctx, _quotes, beats = lab
    mint = f"GATE_{uuid4().hex[:8]}"
    closed = NOW.replace(second=0, microsecond=0) - timedelta(minutes=1)
    not_closed = closed + timedelta(minutes=1)
    observed = closed - timedelta(seconds=20)
    await _plant_curve(
        db_session_factory,
        mint,
        [(observed, "34", "946000000")],
        created_at=closed - timedelta(seconds=120),
    )
    observation = CurveObservation(
        observed_at=observed,
        source="pumpfun_rest",
        real_token_reserves=Decimal("666100000"),
        mcap_sol=Decimal("35.94"),
        complete=False,
    )
    rows = [
        build_row(
            MinuteInputs(
                mint=mint,
                end_time=minute,
                created_at=closed - timedelta(seconds=120),
                initial_real_token_reserves=Decimal("793100000"),
                snapshot=observation,
            )
        )
        for minute in (closed, not_closed)
    ]
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_features(session, rows)

    assert closed_minutes(ctx.state, NOW, backlog=3)[-1] == closed
    report = await lab_tick(ctx, now=NOW)
    assert report.minute == closed and report.proposals == 0
    assert report.rows_evaluated >= 1
    refusals = ctx.state.refusals["meme_paper_v0"]
    assert refusals["creator_net_seller_unknown"] >= 1
    assert refusals["curve_volume_1m_unknown"] >= 1
    assert ctx.state.last_gate_minute == closed, "the minute that has not closed was not read"
    heartbeat = beats.written[-1]
    assert heartbeat["lab_last_tick_at"] == NOW.isoformat()
    assert heartbeat["lab_proposals_total"] == "0"
    assert "creator_net_seller_unknown" in heartbeat["lab_gate_refusals"]
    async with role_session(db_session_factory, db_role=WORKER) as session:
        count = await session.scalar(
            text("SELECT count(*) FROM meme_proposals WHERE mint = :mint"), {"mint": mint}
        )
    assert count == 0


# ---- fills ----------------------------------------------------------------------------


async def test_an_approved_proposal_fills_on_the_first_later_snapshot_and_the_future_cannot_move_it(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, quotes, _beats = lab
    rule_set = await _rule_set(db_engine, f"fill_{uuid4().hex[:6]}")
    mint = f"FILL_{uuid4().hex[:8]}"
    decided = NOW - timedelta(seconds=60)
    await _plant_curve(
        db_session_factory,
        mint,
        [
            (decided - timedelta(seconds=30), "31", "1000000000"),  # before the decision
            (decided + timedelta(seconds=30), "32.4", "993000000"),  # the first after it
            (decided + timedelta(seconds=55), "40", "804000000"),  # later, and irrelevant
        ],
        created_at=decided - timedelta(minutes=2),
    )
    proposal = await _approve(
        db_session_factory, mint=mint, rule_set_id=rule_set, decided_at=decided
    )
    report = await lab_tick(ctx, now=NOW)
    assert report.fills.filled == 1
    bet = await _bet_of(db_session_factory, proposal)
    assert bet["proposal_status"] == "filled" and bet["mode"] == "paper" and bet["status"] == "open"
    assert bet["entry_at"] == decided + timedelta(seconds=30)
    assert Decimal(bet["entry"]["snapshot"]["virtual_sol_reserves"]) == Decimal("32.4")
    assert bet["entry"]["fill_delay_snapshots"] == 1
    assert bet["initial_risk_sol"] == Decimal("0.05")
    assert bet["sol_usd_at_entry"] == Decimal("101.4445") and quotes.calls == 1
    assert bet["entry"]["sol_usd"]["source"] == "pumpfun_rest:/sol-price"
    # The leakage test: rewrite the future and the entry does not move.
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(
            session, _snapshot(mint, decided + timedelta(seconds=100), "300", "300000000")
        )
    await lab_tick(ctx, now=NOW + timedelta(seconds=60))
    again = await _bet_of(db_session_factory, proposal)
    assert again["entry"] == bet["entry"] and again["entry_at"] == bet["entry_at"]
    assert again["mark_sol"] > bet["mark_sol"], "only the mark moved with the future"


async def test_without_a_later_snapshot_the_proposal_waits_and_then_is_unfilled_by_name(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    rule_set = await _rule_set(db_engine, f"wait_{uuid4().hex[:6]}")
    mint = f"WAIT_{uuid4().hex[:8]}"
    decided = NOW - timedelta(seconds=30)
    await _plant_curve(
        db_session_factory,
        mint,
        [(decided - timedelta(seconds=5), "31", "1000000000")],
        created_at=decided - timedelta(minutes=2),
    )
    proposal = await _approve(
        db_session_factory, mint=mint, rule_set_id=rule_set, decided_at=decided
    )
    first = await lab_tick(ctx, now=NOW)
    assert first.fills.waiting == 1
    assert (await _bet_of(db_session_factory, proposal))["proposal_status"] == "approved"
    late = await lab_tick(ctx, now=decided + timedelta(seconds=181))
    assert late.fills.unfilled == 1
    row = await _bet_of(db_session_factory, proposal)
    assert row["proposal_status"] == "unfilled" and row["refusal"] == "no_later_snapshot"


async def test_a_pending_proposal_expires_and_a_cancel_command_rejects_one(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    rule_set = await _rule_set(db_engine, f"exp_{uuid4().hex[:6]}", kind="operator")
    ids = [str(uuid4()), str(uuid4())]
    async with role_session(db_session_factory, db_role=WORKER) as session:
        for proposal_id, expires_in in zip(ids, (60, 600), strict=True):
            await session.execute(
                text(
                    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
                    "  expires_at, features_end_time) VALUES (:id, :mint, :rs, 'rules', 'proposed', "
                    "  :at, :exp, :minute)"
                ),
                {
                    "id": proposal_id,
                    "mint": f"EXP_{proposal_id[:8]}",
                    "rs": rule_set,
                    "at": NOW - timedelta(seconds=120),
                    "exp": NOW - timedelta(seconds=120) + timedelta(seconds=expires_in),
                    "minute": NOW.replace(second=0, microsecond=0) - timedelta(minutes=3),
                },
            )
    command_id = str(uuid4())
    async with role_session(db_session_factory, db_role=APP) as session:
        await session.execute(
            text(
                "INSERT INTO meme_operator_commands (id, proposal_id, command, issued_by, issued_at) "
                "VALUES (:id, :proposal, 'cancel', 'user_test', :at)"
            ),
            {"id": command_id, "proposal": ids[1], "at": NOW - timedelta(seconds=5)},
        )
    report = await lab_tick(ctx, now=NOW)
    assert report.expired == 1 and report.cancelled == 1
    statuses = await _one(
        db_session_factory,
        "SELECT (SELECT status FROM meme_proposals WHERE id = :a) AS a, "
        "       (SELECT status FROM meme_proposals WHERE id = :b) AS b, "
        "       (SELECT decided_by FROM meme_proposals WHERE id = :b) AS by, "
        "       (SELECT result FROM meme_operator_commands WHERE id = :c) AS result",
        a=ids[0],
        b=ids[1],
        c=command_id,
    )
    assert statuses["a"] == "expired"
    assert statuses["b"] == "rejected" and statuses["by"] == "user_test"
    assert statuses["result"] == {"status": "applied", "proposal_status": "rejected"}


async def test_the_daily_loss_cap_and_the_size_ceiling_refuse_a_fill_by_name(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    rule_set = await _rule_set(db_engine, f"cap_{uuid4().hex[:6]}")
    decided = NOW - timedelta(seconds=60)
    mints = [f"CAP_{uuid4().hex[:8]}" for _ in range(2)]
    for mint in mints:
        await _plant_curve(
            db_session_factory,
            mint,
            [(decided + timedelta(seconds=30), "32.4", "993000000")],
            created_at=decided - timedelta(minutes=2),
        )
    too_big = await _approve(
        db_session_factory,
        mint=mints[0],
        rule_set_id=rule_set,
        decided_at=decided,
        decision={"size_sol": "0.06"},
    )
    # A closed bet earlier today that lost the whole daily cap, as the ledger would hold it.
    loser = await _approve(
        db_session_factory, mint=mints[1], rule_set_id=rule_set, decided_at=decided
    )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await session.execute(
            text(
                "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, entry_at, entry, "
                "  initial_risk_sol, params, status, exit_at, exit, pnl_sol, r_multiple) VALUES "
                "(:id, :proposal, :rs, :mint, :entry_at, '{}'::jsonb, 0.20, '{}'::jsonb, 'closed', "
                '  :exit_at, \'{"reason": "max_loss"}\'::jsonb, -0.20, -1)'
            ),
            {
                "id": str(uuid4()),
                "proposal": loser,
                "rs": rule_set,
                "mint": mints[1],
                "entry_at": NOW - timedelta(hours=2),
                "exit_at": NOW - timedelta(hours=1),
            },
        )
        await session.execute(
            text(
                "UPDATE meme_proposals SET status = 'filled', bet_id = (SELECT id FROM meme_paper_bets WHERE proposal_id = :p) WHERE id = :p"
            ),
            {"p": loser},
        )
    capped = await _approve(
        db_session_factory, mint=mints[1] + "_B", rule_set_id=rule_set, decided_at=decided
    )
    await _plant_curve(
        db_session_factory,
        mints[1] + "_B",
        [(decided + timedelta(seconds=30), "32.4", "993000000")],
        created_at=decided - timedelta(minutes=2),
    )
    report = await lab_tick(ctx, now=NOW)
    assert report.fills.unfilled == 2 and report.fills.filled == 0
    assert (await _bet_of(db_session_factory, too_big))["refusal"] == "exceeds_max_sol_per_bet"
    assert (await _bet_of(db_session_factory, capped))["refusal"] == "daily_loss_cap"


# ---- exits ----------------------------------------------------------------------------


async def _open_bet(
    ctx: LabContext,
    factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    label: str,
    *,
    kind: str = "research_only",
) -> tuple[str, str, datetime]:
    """A bet opened by the loop itself at ``decided + 30 s``; returns (mint, proposal, entry_at)."""
    rule_set = await _rule_set(engine, f"{label}_{uuid4().hex[:6]}", kind=kind)
    mint = f"{label.upper()}_{uuid4().hex[:8]}"
    decided = NOW - timedelta(seconds=60)
    entry_at = decided + timedelta(seconds=30)
    await _plant_curve(
        factory, mint, [(entry_at, "32.4", "993000000")], created_at=decided - timedelta(minutes=2)
    )
    proposal = await _approve(factory, mint=mint, rule_set_id=rule_set, decided_at=decided)
    assert (await lab_tick(ctx, now=NOW)).fills.filled == 1
    return mint, proposal, entry_at


async def test_a_bet_closes_by_target_on_the_snapshot_after_the_rule_fired(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    mint, proposal, entry_at = await _open_bet(ctx, db_session_factory, db_engine, "target")
    trigger = entry_at + timedelta(seconds=60)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(
            session, _snapshot(mint, trigger, "70", "460000000")
        )  # 4x: target fires
    await lab_tick(ctx, now=trigger + timedelta(seconds=5))
    pending = await _bet_of(db_session_factory, proposal)
    assert pending["status"] == "open", "the sale waits for the next snapshot"
    assert pending["mark_at"] == trigger
    assert pending["exit_intent"]["reason"] == "target"
    assert pending["exit_intent"]["snapshot_observed_at"] == trigger.isoformat()
    assert pending["high_water_x"] > 1
    sale_at = trigger + timedelta(seconds=30)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(
            session, _snapshot(mint, sale_at, "65", "495000000")
        )  # the curve gave back
    tick = await lab_tick(ctx, now=sale_at + timedelta(seconds=5))
    assert tick.bets.closed >= 1  # other tests may leave bets the loop also settles
    closed = await _bet_of(db_session_factory, proposal)
    assert closed["status"] == "closed" and closed["exit_at"] == sale_at
    assert closed["exit"]["reason"] == "target" and closed["exit"]["trigger"] == "rules"
    assert Decimal(closed["exit"]["snapshot"]["virtual_sol_reserves"]) == Decimal(65)
    assert closed["pnl_sol"] > 0
    # Both columns are NUMERIC(28,10): the quotient of two rounded numbers agrees
    # with the stored multiple to the column scale, never bit for bit.
    assert abs(closed["r_multiple"] - closed["pnl_sol"] / closed["initial_risk_sol"]) < Decimal(
        "1e-8"
    )
    assert closed["sol_usd_at_exit"] == Decimal("101.4445")


async def test_a_bet_closes_by_time_stop_when_the_curve_never_moved(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    mint, proposal, entry_at = await _open_bet(ctx, db_session_factory, db_engine, "timestop")
    stop_at = entry_at + timedelta(seconds=900)
    sale_at = stop_at + timedelta(seconds=40)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(
            session, _snapshot(mint, stop_at - timedelta(seconds=1), "32.4", "993000000")
        )
        await insert_snapshot(session, _snapshot(mint, stop_at, "32.4", "993000000"))
        await insert_snapshot(session, _snapshot(mint, sale_at, "32.4", "993000000"))
    await lab_tick(ctx, now=sale_at + timedelta(seconds=5))
    closed = await _bet_of(db_session_factory, proposal)
    assert closed["status"] == "closed"
    assert closed["exit"]["reason"] == "time_stop" and closed["exit_at"] == sale_at
    assert closed["exit_intent"]["snapshot_observed_at"] == stop_at.isoformat()
    assert closed["pnl_sol"] < 0, (
        "a round trip on a still curve loses exactly the fees and the impact"
    )


async def test_a_bet_closes_on_migration_at_the_completed_curve(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    mint, proposal, entry_at = await _open_bet(ctx, db_session_factory, db_engine, "migr")
    complete_at = entry_at + timedelta(seconds=120)
    sale_at = complete_at + timedelta(seconds=30)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(
            session, _snapshot(mint, complete_at, "115", "280000000", complete=True)
        )
        await insert_snapshot(session, _snapshot(mint, sale_at, "115", "280000000", complete=True))
    await lab_tick(ctx, now=sale_at + timedelta(seconds=5))
    closed = await _bet_of(db_session_factory, proposal)
    assert closed["status"] == "closed"
    assert closed["exit"]["reason"] == "migrated" and closed["exit_at"] == sale_at


async def test_sell_now_sells_on_the_next_snapshot_and_answers_the_command(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    mint, proposal, entry_at = await _open_bet(
        ctx, db_session_factory, db_engine, "sell", kind="operator"
    )
    bet_id = (await _bet_of(db_session_factory, proposal))["id"]
    issued_at = entry_at + timedelta(seconds=45)
    command_id = str(uuid4())
    async with role_session(db_session_factory, db_role=APP) as session:
        await session.execute(
            text(
                "INSERT INTO meme_operator_commands (id, bet_id, command, issued_by, issued_at) "
                "VALUES (:id, :bet, 'sell_now', 'user_test', :at)"
            ),
            {"id": command_id, "bet": bet_id, "at": issued_at},
        )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(
            session, _snapshot(mint, issued_at - timedelta(seconds=10), "33", "970000000")
        )
    await lab_tick(ctx, now=issued_at + timedelta(seconds=5))
    still_open = await _bet_of(db_session_factory, proposal)
    assert still_open["status"] == "open", "a snapshot before the order cannot price the sale"
    assert still_open["exit_intent"]["reason"] == "sell_now"
    sale_at = issued_at + timedelta(seconds=20)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, sale_at, "33.5", "960000000"))
    await lab_tick(ctx, now=sale_at + timedelta(seconds=5))
    closed = await _bet_of(db_session_factory, proposal)
    assert closed["status"] == "closed"
    assert closed["exit"]["reason"] == "sell_now" and closed["exit_at"] == sale_at
    assert closed["exit"]["trigger"] == "operator"
    command = await _one(
        db_session_factory,
        "SELECT applied_at, result FROM meme_operator_commands WHERE id = :id",
        id=command_id,
    )
    assert command["applied_at"] is not None
    assert command["result"] == {"status": "applied", "exit_reason": "sell_now"}


async def test_an_exit_that_finds_no_later_snapshot_is_a_rug_at_zero(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    mint, proposal, entry_at = await _open_bet(ctx, db_session_factory, db_engine, "rug")
    trigger = entry_at + timedelta(seconds=60)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, trigger, "70", "460000000"))
    await lab_tick(ctx, now=trigger + timedelta(seconds=5))
    assert (await _bet_of(db_session_factory, proposal))["status"] == "open"
    await lab_tick(ctx, now=trigger + timedelta(seconds=181))
    closed = await _bet_of(db_session_factory, proposal)
    assert closed["status"] == "closed"
    assert closed["exit"]["reason"] == "rug_no_snapshot"
    assert closed["exit"]["pending_reason"] == "target"
    assert closed["pnl_sol"] == -closed["initial_risk_sol"] and closed["r_multiple"] == Decimal(-1)
    assert closed["sol_usd_at_exit"] is None


# ---- views and grants ------------------------------------------------------------------


async def test_the_scoreboard_and_the_desk_report_the_day_and_the_roles_hold_their_grants(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    mint, proposal, entry_at = await _open_bet(ctx, db_session_factory, db_engine, "board")
    trigger, sale_at = entry_at + timedelta(seconds=60), entry_at + timedelta(seconds=90)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, trigger, "70", "460000000"))
        await insert_snapshot(session, _snapshot(mint, sale_at, "65", "495000000"))
    await lab_tick(ctx, now=sale_at + timedelta(seconds=5))
    bet = await _bet_of(db_session_factory, proposal)
    async with role_session(db_session_factory, db_role=APP) as session:
        board = (
            (
                await session.execute(
                    text("SELECT * FROM meme_lab_scoreboard_v1 WHERE rule_set_id = :rs"),
                    {"rs": bet["rule_set_id"]},
                )
            )
            .mappings()
            .one()
        )
        desk = (
            (
                await session.execute(
                    text("SELECT * FROM meme_desk_v1 WHERE proposal_id = :p"), {"p": proposal}
                )
            )
            .mappings()
            .one()
        )
    assert board["day_brt"].isoformat() == "2026-10-05"
    assert (board["bets"], board["closed"], board["wins"], board["rugs"]) == (1, 1, 1, 0)
    assert board["pnl_sol"] == bet["pnl_sol"] and board["r_sum"] == bet["r_multiple"]
    assert board["pnl_usd"] == bet["pnl_sol"] * Decimal("101.4445") and board["unpriced_usd"] == 0
    assert board["max_drawdown_sol"] == 0
    assert desk["status"] == "filled" and desk["bet_status"] == "closed"
    assert desk["origin"] == "operator" and desk["rule_set_kind"] == "research_only"
    assert desk["pnl_sol"] == bet["pnl_sol"] and desk["token_created_at"] is not None

    # The API may decide; it may not touch the quote, and it may not write a bet.
    async with role_session(db_session_factory, db_role=APP) as session:
        await session.execute(
            text(
                'UPDATE meme_proposals SET decision = decision || \'{"note": "ok"}\' WHERE id = :p'
            ),
            {"p": proposal},
        )
    for statement in (
        "UPDATE meme_proposals SET quote = '{}'::jsonb WHERE id = :p",
        "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, entry_at, entry, "
        "  initial_risk_sol, params) VALUES (gen_random_uuid(), :p, :p, 'x', now(), '{}', 1, '{}')",
        "DELETE FROM meme_proposals WHERE id = :p",
    ):
        with pytest.raises((ProgrammingError, DBAPIError), match="permission denied"):
            async with role_session(db_session_factory, db_role=APP) as session:
                await session.execute(text(statement), {"p": proposal})
    # The worker may never delete evidence, and nobody may write a live bet.
    with pytest.raises((ProgrammingError, DBAPIError), match="permission denied"):
        async with role_session(db_session_factory, db_role=WORKER) as session:
            await session.execute(
                text("DELETE FROM meme_paper_bets WHERE id = :b"), {"b": bet["id"]}
            )
    with pytest.raises(DBAPIError, match="every_bet_is_paper"):
        async with role_session(db_session_factory, db_role=WORKER) as session:
            await session.execute(
                text("UPDATE meme_paper_bets SET mode = 'live' WHERE id = :b"), {"b": bet["id"]}
            )
