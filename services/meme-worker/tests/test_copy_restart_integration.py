"""T0, the lane's own downtime and the recomposition of what a hole hid, against a real Postgres (H-037, R2
fix B2/F8): T0 is the instant the source is first up (after recovery, after the stream started); a restart
declares the downtime since the last durable liveness marker as a hole, closes the holes the dead process
left open, blocks every leader until its window is read from the chain's history (fail closed without
it), and re-reads the position of the copies that survived — priced and flagged, censored by name only
when the position cannot be read. Paper only."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pytest

from hunter_meme_worker.copy_history import MintTrace
from hunter_meme_worker.copy_lane import CopyLane

from .copy_fakes import Curve, FakeChain, FakeClock
from .copy_rig import FakeHistory, Rig, addr, bets, gap_rows, mint_address, proposals, rule_set
from .copy_support import T0, buy, gap, sell

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from hunter_meme_worker.copy_history import LeaderHistory
    from hunter_meme_worker.copy_spec import CopySpec

pytestmark = pytest.mark.integration


class Booted:
    def __init__(
        self, lane: CopyLane, clock: FakeClock, chain: FakeChain, runner: asyncio.Task[None]
    ) -> None:
        self.lane, self.clock, self.chain, self.runner = lane, clock, chain, runner
        self.rig = Rig(lane, clock, chain)

    async def settle(self) -> None:
        await self.rig.settle()

    async def die(self) -> None:
        """The process dies: nothing is drained, nothing is written on the way out."""
        self.runner.cancel()
        await asyncio.gather(self.runner, return_exceptions=True)
        await self.lane.executor.shutdown()


async def boot(
    spec: CopySpec,
    factory: async_sessionmaker[AsyncSession],
    at: Any,
    *,
    history: LeaderHistory | None = None,
    chain: FakeChain | None = None,
) -> Booted:
    clock = FakeClock(at)
    chain = chain or FakeChain(clock)
    chain.clock = clock
    lane = CopyLane(
        spec=spec,
        session_factory=factory,
        chain=chain,  # type: ignore[arg-type]
        clock=clock,
        sleep=clock.sleep,
        history=history,
    )
    await lane.start()
    await lane.source_up()
    runner = asyncio.create_task(lane.executor.run(lane.queue))
    return Booted(lane, clock, chain, runner)


@pytest.mark.asyncio
async def test_t0_is_the_instant_the_source_is_first_up_and_it_never_moves(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    clock = FakeClock(T0)
    lane = CopyLane(
        spec=spec,
        session_factory=db_session_factory,
        chain=FakeChain(clock),  # type: ignore[arg-type]
        clock=clock,
        sleep=clock.sleep,
    )
    await lane.start()  # recovered, but the source is not up yet
    lane.on_item(buy(leader, mint, at=T0 + timedelta(seconds=1)))
    assert lane.stats.skipped_by_reason["not_armed"] == 1 and lane.queue.empty()
    clock.advance(seconds=3)
    await lane.source_up()
    assert lane.book.t0 == T0 + timedelta(seconds=3)
    rows = [
        r for r in await gap_rows(db_session_factory, spec) if r["reason"] == "lane_not_started"
    ]
    assert len(rows) == 1 and rows[0]["gap_end"] == lane.book.t0
    # a legs-complete-before-T0 event is not the cohort's
    lane.on_item(buy(leader, mint, at=T0 + timedelta(seconds=2)))
    assert lane.stats.skipped_by_reason["before_t0"] == 1
    # a restart three hours later reads the same T0
    later = await boot(spec, db_session_factory, T0 + timedelta(hours=3))
    assert later.lane.book.t0 == T0 + timedelta(seconds=3)
    await later.die()


@pytest.mark.asyncio
async def test_a_restart_declares_the_downtime_and_blocks_leaders_until_their_window_is_read(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, other, bought_in_the_hole, fresh = addr("A"), addr("B"), mint_address(), mint_address()
    spec = await rule_set(db_engine, leader, other)
    first = await boot(spec, db_session_factory, T0)
    first.clock.advance(seconds=30)
    await first.lane.marker_once()
    last_marker = first.clock.now
    await first.die()
    history = FakeHistory(complete=True, bought=frozenset({bought_in_the_hole}))
    second = await boot(spec, db_session_factory, T0 + timedelta(minutes=10), history=history)
    try:
        await second.settle()
        downtime = [
            r for r in await gap_rows(db_session_factory, spec) if r["reason"] == "worker_downtime"
        ]
        assert len(downtime) == 1 and downtime[0]["stream"] == "copy_leader:*"
        assert (
            downtime[0]["gap_start"] == last_marker and downtime[0]["gap_end"] == second.clock.now
        )
        up_at = second.clock.now
        second.chain.set(fresh, Curve())
        second.clock.advance(seconds=5)  # an event AFTER the hole, but before its window was read
        second.lane.on_item(buy(leader, fresh, at=second.clock.now))
        await second.settle()
        assert second.lane.book.is_blocked(leader)
        await second.lane.recompose_once()
        await second.settle()
        assert sorted(w[0] for w in history.windows) == sorted([leader, other])
        assert all(w[3] == 1000 for w in history.windows)  # capped at 1 000 signatures
        assert all(w[1] == last_marker and w[2] == up_at for w in history.windows)
        assert not second.lane.book.is_blocked(leader) and not second.lane.book.is_blocked(other)
        seen = [
            p for p in await proposals(db_session_factory, spec) if p["mint"] == bought_in_the_hole
        ]
        assert {p["decision"].get("reason") for p in seen} == {"visto_na_lacuna"}
        # the pair bought inside the hole is not "the first" any more; a fresh one is copyable
        second.chain.set(bought_in_the_hole, Curve())
        second.lane.on_item(buy(leader, bought_in_the_hole, at=second.clock.now))
        assert second.lane.stats.skipped_by_reason["already_observed"] >= 1
        second.chain.set(fresh + "x", Curve())
        second.lane.on_item(buy(leader, fresh + "x", at=second.clock.now))
        await second.settle()
        assert len(await bets(db_session_factory, spec)) == 1
    finally:
        await second.die()


@pytest.mark.asyncio
@pytest.mark.parametrize("history_kind", ["none", "incomplete", "down"])
async def test_without_a_complete_history_a_restarted_lane_copies_nobody(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession], history_kind: str
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    first = await boot(spec, db_session_factory, T0)
    first.clock.advance(seconds=30)
    await first.lane.marker_once()
    await first.die()
    history = {
        "none": None,
        "incomplete": FakeHistory(complete=False),
        "down": FakeHistory(boom=True),
    }[history_kind]
    second = await boot(spec, db_session_factory, T0 + timedelta(minutes=10), history=history)
    try:
        for _ in range(3):
            await second.lane.recompose_once()
        second.chain.set(mint, Curve())
        second.clock.advance(seconds=5)
        second.lane.on_item(buy(leader, mint, at=second.clock.now))
        await second.settle()
        assert await bets(db_session_factory, spec) == []
        [reject] = [p for p in await proposals(db_session_factory, spec) if p["mint"] == mint]
        assert reject["decision"]["reason"] == "recomposicao_pendente"
        assert (
            second.lane.book.is_blocked(leader) and second.lane.book.recompositions_pending() == 2
        )
    finally:
        await second.die()


@pytest.mark.asyncio
async def test_a_hole_the_dead_process_left_open_is_closed_at_its_last_marker(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader = addr("A")
    spec = await rule_set(db_engine, leader, addr("B"))
    first = await boot(spec, db_session_factory, T0)
    first.lane.on_item(gap(T0 + timedelta(seconds=5), None, wallet=leader, reason="nats_silent"))
    await first.settle()
    first.clock.advance(seconds=40)
    await first.lane.marker_once()
    last_marker = first.clock.now
    await first.die()
    second = await boot(spec, db_session_factory, T0 + timedelta(minutes=5))
    try:
        await second.settle()
        rows = [r for r in await gap_rows(db_session_factory, spec) if r["reason"] == "nats_silent"]
        assert sorted(r["detail"]["open"] for r in rows) == [False, True]
        closing = next(r for r in rows if not r["detail"]["open"])
        assert closing["gap_end"] == last_marker and closing["stream"] == f"copy_leader:{leader}"
    finally:
        await second.die()


async def _surviving_copy(
    db_engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], history: FakeHistory | None
) -> tuple[Booted, str, str, CopySpec]:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    first = await boot(spec, factory, T0)
    first.chain.set(mint, Curve())
    first.lane.on_item(buy(leader, mint, at=first.clock.now, position_after=1_000_000))
    await first.settle()
    first.clock.advance(seconds=30)
    await first.lane.marker_once()
    await first.die()
    second = await boot(
        spec, factory, T0 + timedelta(minutes=10), history=history, chain=first.chain
    )
    return second, leader, mint, spec


@pytest.mark.asyncio
async def test_a_surviving_copy_whose_position_is_re_read_is_priced_and_flagged_not_censored(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    history = FakeHistory(trace=MintTrace(current_atoms=900_000, peak_atoms=1_000_000))
    second, leader, mint, spec = await _surviving_copy(db_engine, db_session_factory, history)
    try:
        await second.lane.recompose_once()
        assert [t[:2] for t in history.traces] == [(leader, mint)]  # re-read from the entry onwards
        position = next(iter(second.lane.book.open_positions()))
        assert position.contam == "worker_restart_gap" and position.gap_reason is None
        second.clock.advance(seconds=20)
        second.lane.on_item(sell(leader, mint, at=second.clock.now, position_after=0))
        await second.settle()
        [bet] = await bets(db_session_factory, spec)
        assert bet["status"] == "closed" and bet["outcome_quality"] == "measured"  # priced
        assert bet["exit"]["copy"]["contaminated"] == "worker_restart_gap"  # and flagged
    finally:
        await second.die()


@pytest.mark.asyncio
async def test_a_leader_that_sold_during_the_downtime_closes_the_copy_as_soon_as_it_is_re_read(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    history = FakeHistory(trace=MintTrace(current_atoms=0, peak_atoms=1_000_000))
    second, _, _, spec = await _surviving_copy(db_engine, db_session_factory, history)
    try:
        await second.lane.recompose_once()
        await second.settle()
        [bet] = await bets(db_session_factory, spec)
        assert bet["status"] == "closed" and bet["exit"]["reason"] == "leader_exit_full"
        assert bet["outcome_quality"] == "measured"
        assert bet["exit"]["copy"]["contaminated"] == "worker_restart_gap"
    finally:
        await second.die()


@pytest.mark.asyncio
async def test_a_surviving_copy_whose_position_cannot_be_read_keeps_its_exit_censored_by_name(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    history = FakeHistory(trace=None)
    second, leader, mint, spec = await _surviving_copy(db_engine, db_session_factory, history)
    try:
        await second.lane.recompose_once()
        second.clock.advance(seconds=20)
        second.lane.on_item(sell(leader, mint, at=second.clock.now, position_after=0))
        await second.settle()
        [bet] = await bets(db_session_factory, spec)
        assert bet["outcome_quality"] == "indeterminate"
        assert bet["outcome_quality_reason"] == "worker_restart_gap"
    finally:
        await second.die()


@pytest.mark.asyncio
async def test_a_closed_hole_whose_window_was_not_read_is_still_owed_after_another_restart(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader = addr("A")
    spec = await rule_set(db_engine, leader, addr("B"))
    hole_start = T0 + timedelta(seconds=5)
    first = await boot(spec, db_session_factory, T0)  # no history: the window cannot be read
    first.lane.on_item(gap(hole_start, None, wallet=leader, reason="no_coverage:a+b"))
    first.lane.on_item(
        gap(hole_start, hole_start + timedelta(seconds=20), wallet=leader, reason="no_coverage:a+b")
    )
    await first.settle()
    first.clock.advance(seconds=40)
    await first.lane.marker_once()
    await first.die()
    second_history = FakeHistory(complete=True)
    second = await boot(
        spec, db_session_factory, T0 + timedelta(minutes=10), history=second_history
    )
    await second.lane.recompose_once()
    await second.settle()
    assert hole_start in [w[1] for w in second_history.windows if w[0] == leader]  # it came back
    await second.die()
    third_history = FakeHistory(complete=True)
    third = await boot(spec, db_session_factory, T0 + timedelta(minutes=20), history=third_history)
    try:
        await third.lane.recompose_once()
        await third.settle()
        # recorded as recomposed: not owed again; the second life's own downtime is
        assert hole_start not in [w[1] for w in third_history.windows]
        assert third_history.windows
    finally:
        await third.die()


@pytest.mark.asyncio
async def test_a_source_health_hole_left_open_is_not_promoted_to_a_global_downtime_at_restart(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader = addr("A")
    spec = await rule_set(db_engine, leader, addr("B"))
    first = await boot(spec, db_session_factory, T0)
    first.lane.on_item(gap(T0 - timedelta(hours=1), None, wallet=leader, reason="nats_silent"))
    await first.settle()
    first.clock.advance(seconds=40)
    await first.lane.marker_once()
    last_marker = first.clock.now
    await first.die()
    second = await boot(spec, db_session_factory, T0 + timedelta(minutes=2))
    try:
        await second.settle()
        downtime = [
            r for r in await gap_rows(db_session_factory, spec) if r["reason"] == "worker_downtime"
        ]
        assert len(downtime) == 1 and downtime[0]["gap_start"] == last_marker  # NOT an hour earlier
        assert second.lane.book.recompositions_pending() == 2  # only the downtime's two leaders
    finally:
        await second.die()


@pytest.mark.asyncio
async def test_a_sale_arriving_before_the_first_re_read_is_priced_when_the_position_is_readable(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    history = FakeHistory(trace=MintTrace(current_atoms=0, peak_atoms=1_000_000))
    second, leader, mint, spec = await _surviving_copy(db_engine, db_session_factory, history)
    try:
        second.clock.advance(seconds=1)  # the leader's sale arrives BEFORE any recompose_once ran
        second.lane.on_item(sell(leader, mint, at=second.clock.now, position_after=0))
        await second.settle()
        [bet] = await bets(db_session_factory, spec)
        assert bet["outcome_quality"] == "measured"  # read, then priced - not censored
        assert bet["exit"]["copy"]["contaminated"] == "worker_restart_gap"
        assert history.traces  # and the read really happened
    finally:
        await second.die()


@pytest.mark.asyncio
async def test_the_downtime_is_durable_the_moment_the_source_is_up_before_any_queue_drains(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """R2 round 4 (MF4): the marker used to move to 'now' first and the downtime hole was only queued - a
    second crash in that gap forgot the stretch between the first crash and the first restart."""
    leader = addr("A")
    spec = await rule_set(db_engine, leader, addr("B"))
    first = await boot(spec, db_session_factory, T0)
    first.clock.advance(seconds=30)
    await first.lane.marker_once()
    last_marker = first.clock.now
    await first.die()
    clock = FakeClock(T0 + timedelta(minutes=10))
    lane = CopyLane(
        spec=spec,
        session_factory=db_session_factory,
        chain=FakeChain(clock),  # type: ignore[arg-type]
        clock=clock,
        sleep=clock.sleep,
    )
    await lane.start()
    await lane.source_up()  # NO executor is running: nothing can drain a queue
    rows = [r for r in await gap_rows(db_session_factory, spec) if r["reason"] == "worker_downtime"]
    assert len(rows) == 1 and rows[0]["gap_start"] == last_marker  # durable already, closed
