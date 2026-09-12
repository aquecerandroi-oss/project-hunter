# pyright: reportPrivateUsage=false
"""T4.16 against a real Postgres at ``head`` — one file, one container.

What only a database can prove: the ``0030`` seed parses into ``flow_v2/1``
(15-second clock) and ``hype_probe_v0/2`` (minute clock, pedigree on); the
fast lane's fold reads ``meme_curve_snapshots`` with ``received_at <= as_of``
(the look-ahead test against Postgres: a photo with a block time inside the
window but delivered after the instant is not in the row); a 15-second row
that passes the flow gate becomes an approved proposal stamped with its
``as_of`` and filled on the **next 15-second photo** (``decision_to_fill_s``
measured, in the heartbeat); the pedigree refuses a serial creator and a
ticker clone from ``meme_tokens`` alone; and a close without a photo is
``indeterminate`` — out of the scoreboard's sums, out of the loop's wallet,
counted in the heartbeat.

Run alone (``timeout 590``): it shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.fast_lane import fold_fast
from hunter_meme_worker.features_fast import Fast15sRow
from hunter_meme_worker.lab import LabContext, LabState, heartbeat_fields, lab_tick
from hunter_meme_worker.lab_repo import load_active_rule_sets
from hunter_meme_worker.lab_repo_bets import wallet_state
from hunter_meme_worker.lab_repo_fast import pedigree_for
from hunter_meme_worker.repo import insert_snapshot, upsert_token
from hunter_meme_worker.repo_fast import insert_fast_rows
from hunter_meme_worker.tracker import MintTracker, TrackedMint

from .test_lab_persistence import (  # pyright: ignore[reportPrivateUsage]
    FakeQuotes,
    Heartbeats,
    _bet_of,
    _one,
    _open_bet,
    _plant_curve,
    _snapshot,
    _token,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
FLOW_V2_ID = "01994d00-6c1a-7000-8000-000000000008"
HYPE_PROBE_2_ID = "01994d00-6c1a-7000-8000-000000000009"
CREATED = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
"""A Brasília morning (09:00 BRT) inside the 2026-10 partitions."""
DECISION: dict[str, Any] = {"size_sol": "0.05", "target_x": "3", "trailing_pct": "35"}


@pytest_asyncio.fixture
async def lab(db_session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[LabContext]:
    yield LabContext(
        config=MemeConfig(enabled=True, lab_enabled=True),
        session_factory=db_session_factory,
        state=LabState(),
        quotes=FakeQuotes(),
        heartbeat=Heartbeats(),
    )


def _radar(factory: async_sessionmaker[AsyncSession]) -> RadarContext:
    """A radar context with no boards, tape or risk: the fold reads the database alone."""
    return RadarContext(
        config=MemeConfig(enabled=True),
        session_factory=factory,
        tracker=MintTracker(window_minutes=1440, cap=200),
        state=RadarState(),
        events=None,  # type: ignore[arg-type]
        curves=None,  # type: ignore[arg-type]
        chain=None,  # type: ignore[arg-type]
    )


async def _flow_set(engine: AsyncEngine) -> str:
    """A rule set of this test's own, copying the seeded ``flow_v2/1`` params (owner write)."""
    rule_set_id = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref) "
                "SELECT :id, :name, '1', 'research_only', params, code_ref, 'EXP-M5' "
                "FROM meme_rule_sets WHERE id = :seed"
            ),
            {"id": rule_set_id, "name": f"flow_test_{uuid4().hex[:8]}", "seed": FLOW_V2_ID},
        )
    return rule_set_id


async def _plant_token(
    factory: async_sessionmaker[AsyncSession],
    mint: str,
    *,
    created_at: datetime,
    creator: str,
    symbol: str,
) -> None:
    async with role_session(factory, db_role=WORKER) as session:
        row = replace(
            _token(mint, created_at=created_at), creator=creator, symbol=symbol, name=symbol
        )
        await upsert_token(session, row)


def _fast_row(mint: str, as_of: datetime, observed_at: datetime, **overrides: Any) -> Fast15sRow:
    base: dict[str, Any] = {
        "as_of": as_of,
        "mint": mint,
        "features_version": "meme_features_15s_v1",
        "snapshot_observed_at": observed_at,
        "snapshot_source": "pumpfun_rest",
        "snapshots_120s": 8,
        "age_s": int((as_of - CREATED).total_seconds()),
        "mcap_sol": Decimal("36"),
        "mcap_delta_60s": Decimal("6"),
        "mcap_slope_60s": Decimal("0.18"),
        "window_reason": None,
        "curve_progress_pct": Decimal("0.16"),
        "progress_delta_60s": Decimal("0.02"),
        "progress_rising": True,
        "progress_reason": None,
        "holders": 12,
        "holders_prev": 9,
        "holders_rising": True,
        "holders_reason": None,
        "buys_60s": 20,
        "sells_60s": 8,
        "unique_buyers_60s": 14,
        "net_sol_flow_60s": Decimal("0.9"),
        "curve_volume_60s_sol": Decimal("20"),
        "tape_reason": None,
        "creator_net_seller": False,
        "creator_net_seller_reason": None,
        "dev_share": Decimal("0.05"),
        "dev_share_reason": None,
        "snipers": 1,
        "snipers_reason": None,
    }
    base.update(overrides)
    return Fast15sRow(**base)


# ---- the seed ---------------------------------------------------------------------------


async def test_the_seed_plants_the_flow_arm_on_the_15s_clock_and_the_probe_on_the_minute(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with role_session(db_session_factory, db_role=WORKER) as session:
        specs = {s.label: s for s in await load_active_rule_sets(session)}
    flow, probe = specs["flow_v2/1"], specs["hype_probe_v0/2"]
    assert (flow.id, probe.id) == (FLOW_V2_ID, HYPE_PROBE_2_ID)
    assert flow.clock == "15s" and probe.clock == "1m"
    assert flow.pedigree_exclusions and probe.pedigree_exclusions
    assert flow.exp_ref == "EXP-M5" and probe.exp_ref == "EXP-M5"
    gate = flow.gate
    assert (gate.min_age_s, gate.max_age_s, gate.min_progress_pct) == (30, 300, Decimal(5))
    assert gate.require_positive_flow and gate.min_unique_buyers == 10
    assert gate.max_sells_to_buys == Decimal("0.6") and gate.require_holders_rising
    assert gate.require_progress_rising and gate.max_snipers == 2
    assert gate.max_dev_share == Decimal("0.10") and not gate.dev_share_unknown_allowed
    assert (flow.size_sol, flow.target_x, flow.trailing_pct) == (
        Decimal("0.05"),
        Decimal(3),
        Decimal(35),
    )
    assert flow.trailing_arm_x == Decimal("1.5") and flow.max_hold_s == 1800
    assert flow.max_loss_pct == Decimal(50) and flow.exit_on_line_break
    assert probe.gate.min_hype_score == Decimal("0.6") and probe.gate.min_unique_buyers == 10
    assert probe.scales and probe.scale_gate == "trendline_v0/1"
    assert "meme_paper_v0/1" in specs and "hype_probe_v0/1" in specs, (
        "retired by the script, not here"
    )


# ---- the fold against Postgres: received_at bounds the instant ----------------------------


async def test_the_fast_fold_reads_only_the_photos_received_by_the_instant(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    mint = f"FOLD_{uuid4().hex[:8]}"
    t0 = CREATED + timedelta(seconds=120)
    series = {-75: "30", -60: "30.5", -45: "31", -30: "32", -15: "33", 0: "34"}
    # Tokens fixed at 1e9: the generated mcap_sol is then exactly the SOL figure.
    points = [(t0 + timedelta(seconds=s), sol, "1000000000") for s, sol in series.items()]
    await _plant_curve(db_session_factory, mint, points, created_at=CREATED)
    radar = _radar(db_session_factory)
    tracked = TrackedMint(
        mint=mint,
        first_seen_at=CREATED,
        created_at=CREATED,
        initial_real_token_reserves=Decimal("793100000"),
    )
    as_of = t0 + timedelta(seconds=2)
    (row,) = await fold_fast(radar, [tracked], as_of=as_of)
    assert row.snapshot_observed_at == t0 and row.snapshots_120s == 6
    assert row.mcap_delta_60s == Decimal("3.5000000000"), "34 SOL now minus 30.5 SOL at -60 s"
    assert row.mcap_sol == Decimal("34.0000000000") and row.progress_delta_60s == 0
    assert row.progress_rising is False and row.holders_reason == "no_holders_reader"
    assert row.tape_reason == "no_trade_feed" and row.age_s == 122
    stored = await _one(
        db_session_factory,
        "SELECT mcap_delta_60s, snapshots_120s, window_reason FROM meme_features_15s "
        "WHERE mint = :m AND as_of = :t",
        m=mint,
        t=as_of,
    )
    assert stored["mcap_delta_60s"] == Decimal("3.5000000000") and stored["snapshots_120s"] == 6
    # The leakage test: a photo whose block time is inside the window but which
    # the chain delivered after the instant (received_at > as_of) does not exist
    # for that instant — and does exist one second after it was received.
    late_at = t0 + timedelta(seconds=1)
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_curve_snapshots (observed_at, mint, source, received_at, "
                "  virtual_sol_reserves, virtual_token_reserves, real_sol_reserves, "
                "  real_token_reserves, total_supply, complete) VALUES (:at, :mint, 'solana_rpc', "
                "  :received, 300, 300000000, 270, 20100000, 1000000000, false)"
            ),
            {"at": late_at, "mint": mint, "received": as_of + timedelta(seconds=5)},
        )
    (again,) = await fold_fast(radar, [tracked], as_of=as_of + timedelta(seconds=1))
    assert again.snapshot_observed_at == t0 and again.mcap_delta_60s == row.mcap_delta_60s
    assert again.mcap_sol == row.mcap_sol, "the future is not an input of the present"
    (seen,) = await fold_fast(radar, [tracked], as_of=as_of + timedelta(seconds=6))
    assert seen.snapshot_observed_at == late_at and seen.mcap_sol == Decimal("1000.0000000000")


# ---- the 15-second gate → proposal → fill on the next photo -------------------------------


async def test_a_15s_row_becomes_a_proposal_filled_on_the_next_15s_photo_and_the_delay_is_measured(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    rule_set = await _flow_set(db_engine)
    mint = f"FLOW_{uuid4().hex[:8]}"
    await _plant_token(
        db_session_factory, mint, created_at=CREATED, creator=f"C_{mint}", symbol=f"S{mint[5:9]}"
    )
    photo = CREATED + timedelta(seconds=120)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, photo, "34", "946000000"))
        await insert_fast_rows(session, [_fast_row(mint, photo + timedelta(seconds=2), photo)])
    tick_1 = photo + timedelta(seconds=3)
    report = await lab_tick(lab, now=tick_1)
    assert report.proposals >= 1 and report.fills.filled == 0
    proposal = await _one(
        db_session_factory,
        "SELECT id, status, decided_by, decided_at, features_end_time, reasons FROM meme_proposals "
        "WHERE mint = :m AND rule_set_id = CAST(:rs AS uuid)",
        m=mint,
        rs=rule_set,
    )
    assert proposal["status"] == "approved" and proposal["decided_by"] == "rules"
    assert proposal["decided_at"] == tick_1 and proposal["features_end_time"] == photo + timedelta(
        seconds=2
    )
    assert proposal["reasons"][0] == {"rule": "fluxo_e_holders/1", "series": "meme_features_15s_v1"}
    assert any(r.get("feature") == "pedigree" for r in proposal["reasons"])
    assert lab.state.last_fast_as_of is not None
    assert lab.state.last_fast_as_of >= photo + timedelta(seconds=2), "judged up to this row"
    # The same row is not judged twice by this process; the next photo, 15 s later, fills.
    assert lab.state.fast_rows_evaluated >= 1
    await lab_tick(lab, now=tick_1 + timedelta(seconds=5))
    once = await _one(
        db_session_factory,
        "SELECT count(*) AS n FROM meme_proposals WHERE mint = :m AND rule_set_id = CAST(:rs AS uuid)",
        m=mint,
        rs=rule_set,
    )
    assert once["n"] == 1, "the row was judged once by this process"
    next_photo = photo + timedelta(seconds=15)  # observed_at > decided_at: the fill
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, next_photo, "35", "930000000"))
    report = await lab_tick(lab, now=tick_1 + timedelta(seconds=15))
    assert report.fills.filled >= 1, "the seeded flow_v2/1 proposed on the same row and fills too"
    bet = await _bet_of(db_session_factory, str(proposal["id"]))
    assert bet["status"] == "open" and bet["entry_at"] == next_photo
    assert bet["entry"]["decision_to_fill_s"] == 12, "photo at +15 s minus the decision at +3 s"
    assert bet["outcome_quality"] == "measured" and bet["outcome_quality_reason"] is None
    fields = heartbeat_fields(lab.state)
    assert fields["lab_decision_to_fill_s_p50"] == "12", "measured on the fill, not assumed"
    assert (
        int(fields["lab_decision_to_fill_n"]) >= 1 and int(fields["lab_fast_proposals_total"]) >= 1
    )


# ---- the pedigree from meme_tokens alone ---------------------------------------------------


async def test_the_pedigree_refuses_a_serial_creator_and_a_ticker_clone_from_the_tokens_table(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    rule_set = await _flow_set(db_engine)
    serial, clone = f"SERIAL_{uuid4().hex[:8]}", f"CLONE_{uuid4().hex[:8]}"
    creator, ticker = f"C_{serial}", f"T{clone[6:10]}"
    await _plant_token(db_session_factory, serial, created_at=CREATED, creator=creator, symbol="S1")
    for i in range(2):  # two earlier launches by the same creator inside the hour
        await _plant_token(
            db_session_factory,
            f"PRIOR{i}_{serial}",
            created_at=CREATED - timedelta(minutes=10 * (i + 1)),
            creator=creator,
            symbol=f"P{i}",
        )
    await _plant_token(
        db_session_factory, clone, created_at=CREATED, creator=f"C_{clone}", symbol=ticker
    )
    for i in range(3):  # three more coins with the ticker in the last 24 h, one of them later
        await _plant_token(
            db_session_factory,
            f"TWIN{i}_{clone}",
            created_at=CREATED + timedelta(hours=1) if i == 2 else CREATED - timedelta(hours=i + 1),
            creator=f"C_TWIN{i}",
            symbol=ticker,
        )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        pedigree = await pedigree_for(session, [serial, clone])
    assert pedigree[serial].creator_prior_mints_1h == 2 and pedigree[serial].symbol_dup_24h == 0
    assert pedigree[clone].symbol_dup_24h == 2, "the launch that came later is not a prior clone"
    photo = CREATED + timedelta(seconds=120)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        for mint in (serial, clone):
            await insert_snapshot(session, _snapshot(mint, photo, "34", "946000000"))
        await insert_fast_rows(
            session, [_fast_row(m, photo + timedelta(seconds=2), photo) for m in (serial, clone)]
        )
    report = await lab_tick(lab, now=photo + timedelta(seconds=3))
    name = (
        await _one(
            db_session_factory,
            "SELECT name FROM meme_rule_sets WHERE id = CAST(:rs AS uuid)",
            rs=rule_set,
        )
    )["name"]
    refusals = lab.state.refusals[name]
    assert refusals.get("creator_serial") == 1, refusals
    assert "symbol_clone" not in refusals, "two others = the study's threshold not crossed (3+)"
    proposed = await _one(
        db_session_factory,
        "SELECT count(*) FILTER (WHERE mint = :serial) AS serial, "
        "       count(*) FILTER (WHERE mint = :clone) AS clone "
        "FROM meme_proposals WHERE rule_set_id = CAST(:rs AS uuid)",
        serial=serial,
        clone=clone,
        rs=rule_set,
    )
    assert (proposed["serial"], proposed["clone"]) == (0, 1), (
        "the clone with two twins passes; the serial creator does not"
    )
    assert report.proposals >= 1


# ---- the honest scoreboard against Postgres -----------------------------------------------


async def test_a_close_without_a_photo_is_indeterminate_and_leaves_every_sum(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    mint, proposal, entry_at = await _open_bet(lab, db_session_factory, db_engine, "indet")
    trigger = entry_at + timedelta(seconds=60)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, trigger, "70", "460000000"))
    await lab_tick(lab, now=trigger + timedelta(seconds=5))
    report = await lab_tick(lab, now=trigger + timedelta(seconds=181))
    assert report.bets.closed == 1
    closed = await _bet_of(db_session_factory, proposal)
    assert closed["exit"]["reason"] == "rug_no_snapshot" and closed["exit"]["outcome_quality"] == (
        "indeterminate"
    )
    assert closed["outcome_quality"] == "indeterminate"
    assert closed["outcome_quality_reason"] == "no_snapshot_in_window"
    assert closed["outcome_quality_at"] == closed["exit_at"]
    assert closed["pnl_sol"] == -closed["initial_risk_sol"], "the row keeps the doctrine's number"
    board = await _one(
        db_session_factory,
        "SELECT closed, indeterminate, wins, pnl_sol, r_sum, rugs FROM meme_lab_scoreboard_v1 "
        "WHERE rule_set_id = CAST(:rs AS uuid)",
        rs=closed["rule_set_id"],
    )
    assert (board["closed"], board["indeterminate"], board["wins"], board["rugs"]) == (1, 1, 0, 1)
    assert board["pnl_sol"] is None and board["r_sum"] is None, "no measured close: no sum"
    async with role_session(db_session_factory, db_role=WORKER) as session:
        specs = {s.id: s for s in await load_active_rule_sets(session)}
        wallet = await wallet_state(
            session,
            specs[str(closed["rule_set_id"])],
            day_start=entry_at - timedelta(hours=12),
            day_end=entry_at + timedelta(hours=12),
        )
    assert wallet.realized_today_sol == 0 and wallet.balance_sol == Decimal("2.0"), (
        "the loop's wallet does not count the artefact: the daily cap cannot latch on it"
    )
    assert int(heartbeat_fields(lab.state)["lab_bets_indeterminate_total"]) >= 1
