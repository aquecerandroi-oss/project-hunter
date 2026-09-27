# pyright: reportPrivateUsage=false
"""EXP-M26 R1 against a real Postgres at ``head`` — the first-opportunity record.

What only a database can prove (design §7, R1 acceptance): one row per
(rule set, mint), written by the 1-minute lane on the first pass of the pure
gate with the inputs of that tick; a later pass never replaces it; the proposal
is linked (idempotently, also after a restart); a failed proposal leaves the
opportunity with its reason; a failed row leaves a durable ``write_failed``
marker; a pass the lane could not record makes the next one
``earlier_pass_unrecorded``, never a substitute; a crash before the commit
re-evaluates the same first minute; nothing prunes it; zero EXP-M26 sets write
nothing; and the bounded photo read does not leak its timeout.

The set is this file's own (``…00b6``, test-only), not ``0067``'s seed, so these
tests hold whether or not the arms are seeded.
"""

from __future__ import annotations

import json
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
from hunter_indicators.meme.lines import LinePoint
from hunter_indicators.meme.pedigree import PedigreeFeatures
from hunter_meme_worker import lab_opportunities
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.features import CurveObservation, MinuteInputs, build_row
from hunter_meme_worker.features_tape import TapeMinute
from hunter_meme_worker.lab import LabContext, LabState, _gate_step
from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.lab_opportunities import MatureOpportunityState, mature_gate_step
from hunter_meme_worker.lab_repo import open_mints_for
from hunter_meme_worker.lab_repo_mayhem import load_gate_rows_with_mayhem
from hunter_meme_worker.lab_repo_opportunities import bounded_line_points
from hunter_meme_worker.repo import insert_features

from .test_lab_persistence import FakeQuotes, Heartbeats, _plant_curve

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
VERSION = "meme_features_v3"
SPEC_ID = "01994d00-6c1a-7000-8000-0000000000b6"
T = datetime(2026, 10, 7, 15, 30, tzinfo=UTC)
CLEAN = PedigreeFeatures(0, 0, 0, 0)
SERIAL = PedigreeFeatures(50, 0, 0, 0)
PARAMS: dict[str, Any] = {
    "gate_key": "grafico_maduro_teste", "gate_version": 1, "clock": "1m",
    "min_age_s": 900, "max_age_s": 7200, "require_progress": True,
    "min_progress_pct": "5", "max_progress_pct": "90", "max_participation_pct": "1",
    "require_creator_not_net_seller": False, "exclude_mayhem": True,
    "pedigree_exclusions": True, "pedigree_repeat_dumper": False,
    "size_sol": "0.07", "max_sol_per_bet": "0.07", "max_exposure_per_mint_sol": "0.07",
    "target_x": "1.15", "trailing_pct": "10", "max_hold_s": 300, "max_loss_pct": "50",
    "wallet_max_sol": "100.0", "daily_loss_cap_sol": "10.0", "max_open_positions": 25,
}  # fmt: skip


@pytest_asyncio.fixture(autouse=True)
async def leave_no_trace(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """The database is shared by the whole suite: this file's set, proposals and
    rows go away after each test (owner writes), so no other test sees an extra
    active set or ``approved`` proposals waiting for a fill."""
    yield
    async with db_engine.begin() as connection:
        for statement in (
            "DELETE FROM meme_mature_opportunities WHERE rule_set_id = :id",
            "DELETE FROM meme_proposals WHERE rule_set_id = :id",
            "DELETE FROM meme_rule_sets WHERE id = :id",
        ):
            await connection.execute(text(statement), {"id": SPEC_ID})


async def _spec(engine: AsyncEngine) -> RuleSetSpec:
    async with engine.begin() as connection:  # the owner: a test-only set
        await connection.execute(
            text(
                "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref) "
                "VALUES (:id, 'grafico_teste_r1', '1', 'research_only', CAST(:p AS jsonb), "
                "  'tests', 'EXP-M26') ON CONFLICT (name, version) DO NOTHING"
            ),
            {"id": SPEC_ID, "p": json.dumps(PARAMS)},
        )
    return RuleSetSpec.from_params(
        id=SPEC_ID, name="grafico_teste_r1", version="1", kind="research_only",
        exp_ref="EXP-M26", status="active", code_ref="tests", params=PARAMS,
    )  # fmt: skip


async def _coin(
    factory: async_sessionmaker[AsyncSession], at: datetime, *, minutes: int = 1
) -> str:
    """A coin 930 s old at ``at``, photographed every 60 s since birth, one folded
    minute per ``minutes`` (T, T+1, …): on the curve, 16 %, 10 SOL of volume."""
    mint = f"R1{uuid4().hex[:24]}"
    born = at - timedelta(seconds=930)
    last = at + timedelta(minutes=minutes - 1)
    instants = [born + timedelta(seconds=15 + 60 * k) for k in range(40)]
    instants = [p for p in instants if p <= last - timedelta(seconds=5)]
    await _plant_curve(
        factory, mint, [(p, "36", "1000000000") for p in instants], created_at=born,
        creator=f"C{mint}", symbol=f"S{mint}",
    )  # fmt: skip
    for k in range(minutes):
        end = at + timedelta(minutes=k)
        seen = max(p for p in instants if p <= end)
        points = [LinePoint(p, p, Decimal(36)) for p in instants if p <= end]
        row = build_row(
            MinuteInputs(
                mint=mint, end_time=end, created_at=born,
                initial_real_token_reserves=Decimal("793100000"),
                snapshot=CurveObservation(
                    observed_at=seen, source="pumpfun_rest",
                    real_token_reserves=Decimal("666100000"), mcap_sol=Decimal(36), complete=False,
                ),
                tape=TapeMinute(
                    buys=15, sells=2, unique_buyers=10, net_sol_flow=Decimal(5),
                    volume_sol=Decimal(10), creator_sold=False, creator_net_seller=False,
                ),
                line_points=points,
            )
        )  # fmt: skip
        async with role_session(factory, db_role=WORKER) as session:
            await insert_features(session, [row])
    return mint


async def _step(
    factory: async_sessionmaker[AsyncSession],
    state: MatureOpportunityState,
    spec: RuleSetSpec,
    minute: datetime,
    *,
    pedigree: dict[str, PedigreeFeatures] | None = None,
    commit: bool = True,
) -> lab_opportunities.MatureStepResult:
    async with factory() as session:
        await session.begin()
        await session.execute(text(f"SET LOCAL ROLE {WORKER}"))
        rows = await load_gate_rows_with_mayhem(session, minute=minute, features_version=VERSION)
        ped = pedigree if pedigree is not None else {r.mint: CLEAN for r in rows}
        result = await mature_gate_step(
            session, state, spec, rows, now=minute + timedelta(seconds=65), ttl_s=180,
            already_open=await open_mints_for(session, spec.id), pedigree=ped, e2b=None,
            features_version=VERSION, minute=minute,
        )  # fmt: skip
        await (session.commit() if commit else session.rollback())
    return result


async def _rows(engine: AsyncEngine, mint: str) -> list[dict[str, Any]]:
    async with engine.connect() as connection:
        found = await connection.execute(
            text("SELECT * FROM meme_mature_opportunities WHERE mint = :m"), {"m": mint}
        )
        return [dict(r) for r in found.mappings()]


async def _proposals(engine: AsyncEngine, mint: str) -> list[dict[str, Any]]:
    async with engine.connect() as connection:
        found = await connection.execute(
            text(
                "SELECT id::text AS id, status, features_end_time FROM meme_proposals "
                "WHERE mint = :m ORDER BY features_end_time"
            ),
            {"m": mint},
        )
        return [dict(r) for r in found.mappings()]


async def _release(engine: AsyncEngine, mint: str) -> None:
    """The desk-side end of a proposal (owner write): the mint is no longer open."""
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE meme_proposals SET status = 'rejected' WHERE mint = :m"), {"m": mint}
        )


async def test_the_first_pass_is_recorded_once_with_the_inputs_of_its_tick(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t = T + timedelta(hours=0)
    spec = await _spec(db_engine)
    mint = await _coin(db_session_factory, t, minutes=2)
    ctx = LabContext(
        config=MemeConfig(enabled=True, lab_enabled=True), session_factory=db_session_factory,
        state=LabState(), quotes=FakeQuotes(), heartbeat=Heartbeats(),
    )  # fmt: skip
    await _gate_step(ctx, [spec], [t], now=t + timedelta(seconds=65))
    [row] = await _rows(db_engine, mint)
    [proposal] = await _proposals(db_engine, mint)
    assert (row["fidelity"], row["no_proposal_reason"], row["proposal_refusals"]) == (
        "faithful", None, [],
    )  # fmt: skip
    assert str(row["proposal_id"]) == proposal["id"] and proposal["status"] == "approved"
    assert (row["features_end_time"], row["evaluated_at"]) == (t, t + timedelta(seconds=65))
    assert row["lane_since"] == t and row["features_version"] == VERSION
    assert row["age_s"] == 930 and row["curve_progress_pct"] == Decimal("0.160131")
    assert row["mcap_sol"] == Decimal(36) and row["participation_pct"] == Decimal("0.7")
    assert row["line_reason"] == "flat" and row["line_points"] == 15
    assert row["features_computed_at"] is not None and row["code_ref"]
    assert row["mayhem_enabled"] is False and row["completed_at"] is None
    assert row["coverage_status"] == "covered_from_birth"
    assert row["coverage"]["truncated_at_birth"] is True
    assert row["gate"][0] == {"rule": "grafico_maduro_teste/1"}
    assert row["pedigree"] == {
        "creator_prior_mints_1h": 0, "symbol_dup_24h": 0,
        "creator_prior_dump_count": 0, "creator_prior_dead_count": 0,
    }  # fmt: skip
    assert row["inputs"]["mint"] == mint and row["inputs"]["mcap_sol"] == "36.0000000000"
    assert ctx.state.mature.written_total == 1
    await _release(db_engine, mint)
    await _gate_step(ctx, [spec], [t + timedelta(minutes=1)], now=t + timedelta(seconds=125))
    assert len(await _proposals(db_engine, mint)) == 2, "the proposals go on as before"
    [again] = await _rows(db_engine, mint)
    assert again["id"] == row["id"], "a later pass never replaces the first"


async def test_a_refusal_of_the_proposal_layer_is_recorded_by_name(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t = T + timedelta(hours=1)
    spec = await _spec(db_engine)
    mint = await _coin(db_session_factory, t)
    await _step(db_session_factory, MatureOpportunityState(), spec, t, pedigree={mint: SERIAL})
    [row] = await _rows(db_engine, mint)
    assert (row["proposal_id"], row["no_proposal_reason"]) == (None, "refused")
    assert row["proposal_refusals"] == ["creator_serial"]
    assert row["pedigree"]["creator_prior_mints_1h"] == 50
    assert await _proposals(db_engine, mint) == []


async def test_a_failed_proposal_leaves_the_opportunity_with_its_reason(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing(session: AsyncSession, drafts: object) -> int:
        await session.execute(text("SELECT 1 / 0"))  # a real SQL error inside the savepoint
        return 0

    monkeypatch.setattr("hunter_meme_worker.lab_repo_opportunities.insert_proposals", failing)
    t = T + timedelta(hours=2)
    spec, state = await _spec(db_engine), MatureOpportunityState()
    mint = await _coin(db_session_factory, t)
    await _step(db_session_factory, state, spec, t)
    [row] = await _rows(db_engine, mint)
    assert (row["proposal_id"], row["no_proposal_reason"]) == (None, "insert_failed")
    assert row["fidelity"] == "faithful" and state.proposal_failed_total == 1
    assert await _proposals(db_engine, mint) == []


async def test_a_row_that_fails_leaves_a_durable_write_failed_marker(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = lab_opportunities._values

    def broken(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {**real(*args, **kwargs), "line_points": -1}  # refused by a CHECK

    monkeypatch.setattr(lab_opportunities, "_values", broken)
    t = T + timedelta(hours=3)
    spec, state = await _spec(db_engine), MatureOpportunityState()
    mint = await _coin(db_session_factory, t, minutes=2)
    await _step(db_session_factory, state, spec, t)
    [row] = await _rows(db_engine, mint)
    assert (row["fidelity"], row["coverage_status"], row["line_points"]) == (
        "write_failed", "unread", None,
    )  # fmt: skip
    assert row["proposal_id"] is not None, "the proposal of the same pass stays linked"
    monkeypatch.setattr(lab_opportunities, "_values", real)
    await _release(db_engine, mint)
    await _step(db_session_factory, state, spec, t + timedelta(minutes=1))
    assert [r["id"] for r in await _rows(db_engine, mint)] == [row["id"]], "no substitute"


async def test_an_unrecorded_pass_makes_the_next_one_unfaithful_in_memory_and_after_a_restart(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def lost(session: AsyncSession, values: object) -> str:
        return "failed"

    real = lab_opportunities.insert_opportunity
    t = T + timedelta(hours=4)
    spec = await _spec(db_engine)
    # (first pass refused by the proposal layer?, restart before the next pass?, expected)
    cases = (
        (True, False, "earlier_pass_unrecorded"),  # no proposal: only the process remembers
        (False, True, "earlier_pass_unrecorded"),  # restart: the earlier proposal is the proof
        (True, True, "eligible_before_lane"),  # both gone: never read as the first (Astra)
    )
    for index, (refused, restart, expected) in enumerate(cases):
        minute = t + timedelta(minutes=10 * index)
        state = MatureOpportunityState()
        mint = await _coin(db_session_factory, minute, minutes=2)
        monkeypatch.setattr(lab_opportunities, "insert_opportunity", lost)
        first = {mint: SERIAL} if refused else None
        await _step(db_session_factory, state, spec, minute, pedigree=first)
        assert state.failed_total == 1 and await _rows(db_engine, mint) == []
        assert (await _proposals(db_engine, mint) == []) is refused
        monkeypatch.setattr(lab_opportunities, "insert_opportunity", real)
        await _release(db_engine, mint)
        later = MatureOpportunityState() if restart else state
        await _step(db_session_factory, later, spec, minute + timedelta(minutes=1))
        [row] = await _rows(db_engine, mint)
        assert row["fidelity"] == expected, (refused, restart)
        assert row["features_end_time"] == minute + timedelta(minutes=1)
        if restart:
            assert row["lane_since"] == minute + timedelta(minutes=1) > minute, "the gap shows"


async def test_a_lost_row_is_recovered_while_the_mint_is_still_open(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Astra, R1 review, must-fix 2: the proposal committed, both writes failed and
    the process restarted; the proposal is still ``approved`` (the mint is open).
    The next pass must record the loss now, not wait for the position to close."""

    async def lost(session: AsyncSession, values: object) -> str:
        return "failed"

    real = lab_opportunities.insert_opportunity
    t = T + timedelta(hours=7)
    spec = await _spec(db_engine)
    mint = await _coin(db_session_factory, t, minutes=2)
    monkeypatch.setattr(lab_opportunities, "insert_opportunity", lost)
    await _step(db_session_factory, MatureOpportunityState(), spec, t)
    monkeypatch.setattr(lab_opportunities, "insert_opportunity", real)
    [proposal] = await _proposals(db_engine, mint)
    assert proposal["status"] == "approved" and await _rows(db_engine, mint) == []
    await _step(db_session_factory, MatureOpportunityState(), spec, t + timedelta(minutes=1))
    [row] = await _rows(db_engine, mint)
    assert row["fidelity"] == "earlier_pass_unrecorded"
    assert (row["no_proposal_reason"], row["proposal_refusals"]) == ("refused", ["already_open"])
    assert len(await _proposals(db_engine, mint)) == 1, "the open mint gets no second proposal"


async def test_a_restart_that_re_evaluates_the_same_minute_links_and_flags_the_lost_row(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Astra, round 2: T's proposal committed, both writes failed, the restarted
    backlog re-evaluates **T** itself — with the mint still open (no draft) and with
    it closed (the draft hits the idempotence key). Both link T's proposal and are
    ``earlier_pass_unrecorded``: the inputs are re-read, not the original envelope."""

    async def lost(session: AsyncSession, values: object) -> str:
        return "failed"

    real = lab_opportunities.insert_opportunity
    spec = await _spec(db_engine)
    for index, still_open in enumerate((True, False)):
        minute = T + timedelta(hours=9, minutes=10 * index)
        mint = await _coin(db_session_factory, minute)
        monkeypatch.setattr(lab_opportunities, "insert_opportunity", lost)
        await _step(db_session_factory, MatureOpportunityState(), spec, minute)
        monkeypatch.setattr(lab_opportunities, "insert_opportunity", real)
        [proposal] = await _proposals(db_engine, mint)
        if not still_open:
            await _release(db_engine, mint)
        await _step(db_session_factory, MatureOpportunityState(), spec, minute)
        [row] = await _rows(db_engine, mint)
        assert str(row["proposal_id"]) == proposal["id"], still_open
        assert (row["fidelity"], row["proposal_refusals"]) == ("earlier_pass_unrecorded", [])
        assert len(await _proposals(db_engine, mint)) == 1


async def test_a_failed_read_of_the_record_never_aborts_the_minute(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Astra, R1 review, must-fix 3: the ``recorded_mints`` read fails with a real SQL
    error after the proposal was inserted; the proposal still commits and the pass
    is remembered as lost."""
    from hunter_meme_worker import lab_repo_opportunities

    monkeypatch.setattr(lab_repo_opportunities, "_RECORDED", text("SELECT 1 / 0 AS mint"))
    t = T + timedelta(hours=8)
    spec, state = await _spec(db_engine), MatureOpportunityState()
    mint = await _coin(db_session_factory, t)
    await _step(db_session_factory, state, spec, t)
    assert len(await _proposals(db_engine, mint)) == 1, "the minute committed"
    assert await _rows(db_engine, mint) == []
    assert state.failed_total == 1 and (SPEC_ID, mint) in state.failed_pairs


async def test_a_crash_before_the_commit_re_evaluates_the_same_first_minute(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t = T + timedelta(hours=5)
    spec = await _spec(db_engine)
    mint = await _coin(db_session_factory, t)
    await _step(db_session_factory, MatureOpportunityState(), spec, t, commit=False)
    assert await _rows(db_engine, mint) == [] and await _proposals(db_engine, mint) == []
    for _ in range(2):  # the restarted backlog, twice: idempotent
        await _step(db_session_factory, MatureOpportunityState(), spec, t)
    [row] = await _rows(db_engine, mint)
    [proposal] = await _proposals(db_engine, mint)
    assert row["features_end_time"] == t and row["fidelity"] == "faithful"
    assert str(row["proposal_id"]) == proposal["id"]


async def test_zero_exp_m26_sets_write_nothing_and_nothing_prunes_the_record(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    t = T + timedelta(hours=6)
    spec = await _spec(db_engine)
    other = replace(spec, exp_ref="EXP-M1")
    mint = await _coin(db_session_factory, t)
    ctx = LabContext(
        config=MemeConfig(enabled=True, lab_enabled=True), session_factory=db_session_factory,
        state=LabState(), quotes=FakeQuotes(), heartbeat=Heartbeats(),
    )  # fmt: skip
    await _gate_step(ctx, [other], [t], now=t + timedelta(seconds=65))
    assert len(await _proposals(db_engine, mint)) == 1 and await _rows(db_engine, mint) == []
    await _release(db_engine, mint)
    await _step(db_session_factory, MatureOpportunityState(), spec, t)
    async with db_engine.begin() as connection:  # age it past every 7-day retention
        await connection.execute(
            text(
                "UPDATE meme_mature_opportunities SET evaluated_at = evaluated_at - interval '40 d', "
                "  features_end_time = features_end_time - interval '40 d', "
                "  lane_since = lane_since - interval '40 d' WHERE mint = :m"
            ),
            {"m": mint},
        )
        can_delete = await connection.scalar(
            text(
                "SELECT has_table_privilege('hunter_worker', 'meme_mature_opportunities', 'DELETE')"
            )
        )
    from hunter_meme_worker.lab_trail import prune_trail_batches

    await prune_trail_batches(db_session_factory, batch=5000)
    assert can_delete is False and len(await _rows(db_engine, mint)) == 1


async def test_the_bounded_photo_read_restores_the_statement_timeout(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with role_session(db_session_factory, db_role=WORKER) as session:
        before = await session.scalar(text("SELECT current_setting('statement_timeout')"))
        points = await bounded_line_points(session, mints=["nobody"], end_time=T)
        after = await session.scalar(text("SELECT current_setting('statement_timeout')"))
    assert points == {"nobody": []} and before == after != "5s"


def test_the_desks_pedigree_subtracts_the_three_arms_bets() -> None:
    from hunter_meme_worker.lab_repo_fast import _PEDIGREE

    sql = str(_PEDIGREE)
    assert sql.count("pb.rule_set_id <> ALL(CAST(:mature_rule_set_ids AS uuid[]))") == 1
    assert sql.count("pb2.rule_set_id <> ALL(CAST(:mature_rule_set_ids AS uuid[]))") == 1
    assert lab_opportunities.MATURE_CHART_RULE_SET_IDS == (
        "01994d00-6c1a-7000-8000-00000000001f",
        "01994d00-6c1a-7000-8000-000000000020",
        "01994d00-6c1a-7000-8000-000000000021",
    )
