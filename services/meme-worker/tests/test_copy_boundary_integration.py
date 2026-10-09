"""The copy lane's boundaries, against a real Postgres (H-037, design §3.6/§4): a copy proposal is never
``proposed`` (the live-order approval path can promote only ``proposed`` rows), the two rule sets keep
separate capacity with the primary protected, T0 and coverage holes are durable, no job outlives the
lane, a close that lost a race to another writer is not counted, a copy that lived across a gap or a
migration is flagged or sent out by name, and the chain's verdicts reach the copy. Paper only."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session

from .copy_fakes import Curve
from .copy_rig import (
    WORKER,
    addr,
    bets,
    mint_address,
    proposals,
    rule_set,
    running,
    running_many,
)
from .copy_support import T0, buy, confirmation, gap, sell

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

_AUDIT = [
    "CREATE TABLE IF NOT EXISTS copy_test_status_audit (rule_set_id uuid, status text)",
    "CREATE OR REPLACE FUNCTION copy_test_audit() RETURNS trigger AS $$ BEGIN "
    "INSERT INTO copy_test_status_audit VALUES (NEW.rule_set_id, NEW.status); RETURN NEW; END; "
    "$$ LANGUAGE plpgsql SECURITY DEFINER",
    "GRANT SELECT ON copy_test_status_audit TO hunter_worker",
    "TRUNCATE copy_test_status_audit",
    "DROP TRIGGER IF EXISTS copy_test_audit_trg ON meme_proposals",
    "CREATE TRIGGER copy_test_audit_trg AFTER INSERT OR UPDATE ON meme_proposals "
    "FOR EACH ROW EXECUTE FUNCTION copy_test_audit()",
]


@pytest.mark.asyncio
async def test_a_copy_proposal_is_born_decided_and_never_exists_as_proposed(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Every status every copy row ever held, recorded by a trigger: none is ``proposed`` — the one
    status ``decide_proposal`` (approval.py:57) can promote to ``live`` — and none is ``live``."""
    async with db_engine.begin() as connection:
        for statement in _AUDIT:
            await connection.execute(text(statement))
    leader, other = addr("A"), addr("B")
    mint, mint2, mint3, mint4 = (mint_address() for _ in range(4))
    spec = await rule_set(db_engine, leader, other)
    try:
        async with running(spec, db_session_factory) as rig:
            rig.chain.set(mint, Curve())
            rig.chain.set(mint2, Curve(complete=True))
            rig.lane.on_item(buy(leader, mint, at=T0))  # admitted and filled
            rig.lane.on_item(buy(leader, mint2, at=T0))  # on the pool: rejected, outside the venue
            rig.lane.on_item(buy(leader, mint4, at=T0))  # admitted, no state: unfilled
            rig.lane.on_item(buy(leader, mint3, at=T0, spent_sol="0.01"))  # rejected
            await rig.settle()
        statuses = {p["status"] for p in await proposals(db_session_factory, spec)}
        assert statuses == {"filled", "unfilled", "rejected"}
        async with role_session(db_session_factory, db_role=WORKER) as session:
            seen = {
                r[0]
                for r in await session.execute(
                    text(
                        "SELECT DISTINCT status FROM copy_test_status_audit WHERE rule_set_id = CAST(:r AS uuid)"
                    ),
                    {"r": spec.id},
                )
            }
            modes = {
                r[0]
                for r in await session.execute(
                    text(
                        "SELECT DISTINCT mode FROM meme_paper_bets WHERE rule_set_id = CAST(:r AS uuid)"
                    ),
                    {"r": spec.id},
                )
            }
        assert seen <= {"approved", "filled", "unfilled", "rejected"} and "proposed" not in seen
        assert modes == {"paper"}
    finally:
        async with db_engine.begin() as connection:
            await connection.execute(
                text("DROP TRIGGER IF EXISTS copy_test_audit_trg ON meme_proposals")
            )


@pytest.mark.asyncio
async def test_each_rule_set_has_its_own_capacity_and_the_secondary_never_blocks_the_primary(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    shared, mint_a, mint_b = addr("S"), mint_address(), mint_address()
    regra = await rule_set(db_engine, shared, addr("R"))
    everton = await rule_set(
        db_engine, shared, addr("E"), max_open_per_stratum=1
    )  # a one-slot secondary: saturated at once
    async with running_many([regra, everton], db_session_factory) as (r_rig, e_rig):
        for mint in (mint_a, mint_b):
            r_rig.chain.set(mint, Curve())
        for rig in (r_rig, e_rig):
            rig.lane.on_item(buy(shared, mint_a, at=T0))
            rig.lane.on_item(buy(shared, mint_b, at=T0))
        await r_rig.settle()
        await e_rig.settle()
        assert len(await bets(db_session_factory, regra)) == 2  # the primary lost nothing
        assert (
            len(await bets(db_session_factory, everton)) == 1
        )  # the secondary hit its own ceiling
        refused = [
            p for p in await proposals(db_session_factory, everton) if p["status"] == "unfilled"
        ]
        assert [p["refusal"] for p in refused] == ["teto_aberto"]
        assert {b["entry"]["copy"]["rule_set"] for b in await bets(db_session_factory, regra)} == {
            "copy_v0/1"
        }
        async with role_session(db_session_factory, db_role=WORKER) as session:
            ids = {
                str(r[0])
                for r in await session.execute(
                    text(
                        "SELECT DISTINCT rule_set_id FROM meme_paper_bets WHERE rule_set_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
                    ),
                    {"a": regra.id, "b": everton.id},
                )
            }
        assert ids == {regra.id, everton.id}


@pytest.mark.asyncio
async def test_t0_and_closed_coverage_holes_are_durable_and_t0_never_moves(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    from hunter_meme_worker.copy_lane import CopyLane

    from .copy_fakes import FakeChain, FakeClock

    leader = addr("A")
    spec = await rule_set(db_engine, leader, addr("B"))
    clock = FakeClock(T0)
    chain = FakeChain(clock)

    def lane() -> CopyLane:
        return CopyLane(
            spec=spec,
            session_factory=db_session_factory,
            chain=chain,  # type: ignore[arg-type]
            clock=clock,
            sleep=clock.sleep,
        )

    first = lane()
    await first.recover()
    t0 = first.book.t0
    clock.advance(hours=3)
    second = lane()  # a restart three hours later
    await second.recover()
    assert t0 == second.book.t0 == T0  # read back, not re-minted
    assert second.fields()["copy_t0"] == T0.isoformat(timespec="milliseconds")
    async with role_session(db_session_factory, db_role=WORKER) as session:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT count(*) AS n, min(gap_end) AS e FROM meme_ingest_gaps "
                        "WHERE stream = 'copy_leader:*' AND reason = 'lane_not_started' "
                        "  AND detail ->> 'rule_set_id' = :r"
                    ),
                    {"r": spec.id},
                )
            )
            .mappings()
            .one()
        )
    assert row["n"] == 1 and row["e"] == T0  # one initial gap, ending at T0
    # a closed hole of one wallet is a meme_ingest_gaps row; an open one waits for its end
    async with running(spec, db_session_factory) as rig:
        rig.lane.on_item(gap(T0, None, wallet=leader, reason="socket_down"))
        rig.lane.on_item(
            gap(
                T0 + timedelta(seconds=1),
                T0 + timedelta(seconds=9),
                wallet=leader,
                reason="socket_down",
            )
        )
        await rig.settle()
    async with role_session(db_session_factory, db_role=WORKER) as session:
        streams = [
            r[0]
            for r in await session.execute(
                text(
                    "SELECT stream FROM meme_ingest_gaps WHERE reason = 'socket_down' "
                    "  AND detail ->> 'rule_set_id' = :r"
                ),
                {"r": spec.id},
            )
        ]
    assert streams == [f"copy_leader:{leader}"]


@pytest.mark.asyncio
async def test_the_executor_caps_jobs_in_flight_and_no_job_outlives_the_lane(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader = addr("A")
    spec = await rule_set(
        db_engine, leader, addr("B"), queue_max=500, max_attempts_per_leader_day=500
    )
    async with running(spec, db_session_factory) as rig:
        gate = asyncio.Event()  # a chain that never answers: the RPC is stuck

        async def stuck(*args: Any, **kwargs: Any) -> Any:
            await gate.wait()

        rig.chain.get_curve_states = stuck  # type: ignore[method-assign]
        for _ in range(60):
            rig.lane.on_item(buy(leader, mint_address(), at=T0))
        await asyncio.sleep(0.3)
        assert rig.lane.executor.in_flight <= 32  # never an unbounded set of tasks
        assert rig.lane.queue.qsize() >= 60 - 32  # the rest waits in the bounded queue
        await rig.lane.executor.shutdown()
        assert rig.lane.executor.in_flight == 0  # cancelled and awaited: nothing writes later
    assert await bets(db_session_factory, spec) == []


@pytest.mark.asyncio
async def test_a_close_that_lost_the_race_to_another_writer_is_not_counted_as_ours(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        rig.lane.on_item(buy(leader, mint, at=T0))
        await rig.settle()
        async with (
            db_engine.begin() as connection
        ):  # the Lab's tick (or an operator) closes it first
            await connection.execute(
                text(
                    "UPDATE meme_paper_bets SET status = 'closed', exit_at = entry_at + interval '1 second', "
                    '  exit = CAST(\'{"reason": "lab"}\' AS jsonb), pnl_sol = 0, r_multiple = 0 '
                    "WHERE rule_set_id = CAST(:r AS uuid)"
                ),
                {"r": spec.id},
            )
        rig.clock.advance(seconds=30)
        rig.lane.on_item(sell(leader, mint, at=rig.clock.now))
        await rig.settle()
        [bet] = await bets(db_session_factory, spec)
        assert bet["exit"] == {"reason": "lab"}  # the other writer's close stands
        assert rig.lane.stats.closed_elsewhere == 1 and rig.lane.stats.exits == 0
        assert rig.lane.book.open_count == 0


@pytest.mark.asyncio
async def test_a_copy_that_lived_across_a_gap_and_hit_the_time_cap_is_priced_but_flagged(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        rig.lane.on_item(buy(leader, mint, at=T0))
        await rig.settle()
        rig.clock.advance(seconds=20)
        rig.lane.on_item(gap(rig.clock.now, rig.clock.now + timedelta(seconds=5), wallet=leader))
        rig.clock.advance(seconds=700)
        await rig.lane.sweep_once()
        await rig.settle()
        [bet] = await bets(db_session_factory, spec)
        assert bet["exit"]["reason"] == "time_cap" and bet["outcome_quality"] == "measured"
        assert bet["exit"]["copy"]["contaminated"] == "leader_gap_exit"
        assert (
            bet["exit"]["sol_received"] != "0"
        )  # priced: a time cap does not depend on the leader


@pytest.mark.asyncio
async def test_a_copy_whose_curve_migrates_is_sent_out_unpriced_when_the_pool_is_not_a_venue(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        rig.lane.on_item(buy(leader, mint, at=T0))
        await rig.settle()
        rig.clock.advance(seconds=5)
        rig.chain.set(mint, Curve(complete=True))
        await rig.lane.mark_once()
        await rig.settle()
        [bet] = await bets(db_session_factory, spec)
        assert bet["outcome_quality"] == "indeterminate"
        assert bet["outcome_quality_reason"] == "migrou_fora_de_praca"


@pytest.mark.asyncio
async def test_a_chain_verdict_item_reaches_the_copy_delay_recorded_or_invalidated_by_name(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, ok_mint, bad_mint = addr("A"), mint_address(), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        for mint in (ok_mint, bad_mint):
            rig.chain.set(mint, Curve())
        good = buy(leader, ok_mint, at=T0, confirmed=False, signature="V-OK")
        bad = buy(leader, bad_mint, at=T0, confirmed=False, signature="V-BAD")
        rig.lane.on_item(good)
        rig.lane.on_item(bad)
        await rig.settle()
        rig.lane.on_item(confirmation(good))
        rig.lane.on_item(confirmation(bad, "failed_tx"))
        await rig.settle()
        by_mint = {b["mint"]: b for b in await bets(db_session_factory, spec)}
        assert by_mint[ok_mint]["entry"]["copy"]["confirmation_delay_ms"] == 700
        assert by_mint[ok_mint]["status"] == "open"
        sold = by_mint[bad_mint]
        assert sold["status"] == "closed" and sold["exit"]["reason"] == "invalidated"
        assert sold["outcome_quality"] == "measured"  # it stays in the primary
        assert sold["entry"]["copy"]["invalid_reason"] == "failed_tx"
        assert rig.lane.stats.invalidated == 1
