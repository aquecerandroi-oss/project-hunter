"""Every persistence failure path of the copy lane, against a real Postgres with injected faults (H-037,
R2 fix B3/B6/B2b): a fact that cannot be written is retried with the same price; past its budget it opens
a **durable global hole** (`funil_indisponivel`) that is not sticky — the next successful write closes it —
and that every leader is recomposed after; a source-health or coverage gap is recorded when it OPENS (a
second row closes it, the table being append-only); the lane's stop drains what it can and records what it
cannot. Paper only."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pytest

from hunter_meme_worker import copy_exec, copy_exec_entry, copy_exec_exit, copy_exec_facts
from hunter_meme_worker.copy_events import RejectEntry, UnverifiedIntent, leader_ref

from .copy_fakes import Curve
from .copy_rig import addr, bets, gap_rows, mint_address, proposals, rule_set, running
from .copy_support import T0, buy, gap, sell

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("fast_retries")]


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(copy_exec, "RETRY_BASE_S", 0.0)
    monkeypatch.setattr(copy_exec, "WAIT_S", 0.0)


def _flaky(real: Any, failures: int) -> tuple[Any, dict[str, int]]:
    counter = {"calls": 0, "failed": 0}

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        counter["calls"] += 1
        if counter["failed"] < failures:
            counter["failed"] += 1
            raise RuntimeError("database blip")
        return await real(*args, **kwargs)

    return wrapper, counter


@pytest.mark.asyncio
async def test_an_entry_write_that_fails_once_lands_on_redelivery_with_one_row(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    flaky, counter = _flaky(copy_exec_entry.open_copy_bet, 1)
    monkeypatch.setattr(copy_exec_entry, "open_copy_bet", flaky)
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        rig.lane.on_item(buy(leader, mint, at=T0))
        await rig.settle()
        [bet] = await bets(db_session_factory, spec)
        assert bet["status"] == "open" and counter == {"calls": 2, "failed": 1}
        assert rig.lane.stats.persist_dropped == 0 and not rig.lane.book.funnel_unavailable


@pytest.mark.asyncio
async def test_an_entry_that_never_lands_opens_a_durable_hole_that_the_next_write_closes(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leader, other, mint = addr("A"), addr("B"), mint_address()
    spec = await rule_set(db_engine, leader, other)
    real = {
        name: getattr(copy_exec_entry, name)
        for name in ("open_copy_bet", "record_gap", "reject_entry", "censor_entry")
    }
    counters: dict[str, tuple[Any, dict[str, int]]] = {}
    for name, fn in real.items():  # the whole database is down
        counters[name] = _flaky(fn, 10_000)
        monkeypatch.setattr(copy_exec_entry, name, counters[name][0])
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        rig.lane.on_item(buy(leader, mint, at=T0))
        await rig.settle()
        # the entry fact was lost for good: the funnel is declared down (a hole, in memory)
        assert counters["open_copy_bet"][1]["calls"] == copy_exec.MAX_RETRIES + 1
        assert rig.lane.book.funnel_unavailable and rig.lane.stats.persist_dropped >= 1
        assert rig.lane.book.occupied("regra") == 0  # the slot was given back
        assert rig.lane.stats.gaps_lost == 1  # the hole's own record could not be written either
        assert (
            await gap_rows(db_session_factory, spec) == []
            and await proposals(db_session_factory, spec) == []
        )
        # the database comes back: the next successful write resumes the funnel (not sticky)
        for name, fn in real.items():
            monkeypatch.setattr(copy_exec_entry, name, fn)
        rig.lane.on_item(buy(other, mint_address(), at=T0 + timedelta(seconds=5)))
        await rig.settle()
        assert not rig.lane.book.funnel_unavailable
        rows = [
            r
            for r in await gap_rows(db_session_factory, spec)
            if r["reason"] == "funil_indisponivel"
        ]
        assert [r["detail"]["open"] for r in rows] == [False]  # the closing row survived
        assert rig.lane.book.recompositions_pending() == 2  # every leader owes its window
        written = await proposals(db_session_factory, spec)
        assert [(p["status"], p["decision"].get("reason")) for p in written] == [
            ("rejected", "lacuna")
        ]
        # and until the windows are recomposed, nobody is copied
        rig.lane.on_item(buy(leader, mint_address(), at=T0 + timedelta(seconds=9)))
        await rig.settle()
        reasons = [p["decision"].get("reason") for p in await proposals(db_session_factory, spec)]
        assert reasons == ["lacuna", "recomposicao_pendente"]


@pytest.mark.asyncio
async def test_a_hole_is_recorded_when_it_opens_and_again_when_it_closes_with_one_gap_id(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader = addr("A")
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        start = T0 + timedelta(seconds=5)
        rig.lane.on_item(gap(start, None, wallet=leader, reason="nats_silent"))
        await rig.settle()
        opened = [
            r for r in await gap_rows(db_session_factory, spec) if r["reason"] == "nats_silent"
        ]
        assert [r["detail"]["open"] for r in opened] == [True]  # durable the moment it opened
        assert opened[0]["gap_end"] - opened[0]["gap_start"] == timedelta(microseconds=1)
        rig.lane.on_item(
            gap(start, start + timedelta(seconds=70), wallet=leader, reason="nats_silent")
        )
        await rig.settle()
        rows = [r for r in await gap_rows(db_session_factory, spec) if r["reason"] == "nats_silent"]
        assert len(rows) == 2 and len({r["detail"]["gap_id"] for r in rows}) == 1
        closing = next(r for r in rows if not r["detail"]["open"])
        assert closing["gap_end"] == start + timedelta(seconds=70)
        assert closing["stream"] == f"copy_leader:{leader}"


@pytest.mark.asyncio
async def test_a_close_that_fails_after_pricing_lands_later_with_the_same_sale(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    flaky, counter = _flaky(copy_exec_exit.close_copy_bet, 2)
    monkeypatch.setattr(copy_exec_exit, "close_copy_bet", flaky)
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        rig.lane.on_item(buy(leader, mint, at=T0))
        await rig.settle()
        rig.clock.advance(seconds=30)
        rig.lane.on_item(sell(leader, mint, at=rig.clock.now))
        await rig.settle()
        [bet] = await bets(db_session_factory, spec)
        assert bet["status"] == "closed" and bet["outcome_quality"] == "measured"
        assert counter["calls"] == 3 and rig.lane.stats.persist_dropped == 0
        assert rig.lane.stats.exits == 1


@pytest.mark.asyncio
async def test_stopping_the_lane_drains_what_can_be_written_and_records_what_cannot(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leader = addr("A")
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        ref = leader_ref(buy(leader, mint_address(), at=T0), "regra")
        stored = RejectEntry(mint_address(), ref, "nao_primeira", T0)
        rig.lane.outbox.append(stored)  # an obligation the executor never got to
        await rig.lane.stop()
        assert [p["status"] for p in await proposals(db_session_factory, spec)] == ["rejected"]
        # now the database refuses a pending funnel fact at stop: the loss is recorded, left OPEN
        monkeypatch.setattr(
            copy_exec_entry, "reject_entry", _flaky(copy_exec_entry.reject_entry, 10_000)[0]
        )
        lost = RejectEntry(mint_address(), ref, "nao_primeira", T0 + timedelta(seconds=3))
        rig.lane.outbox.append(lost)
        await rig.lane.stop()
        holes = [
            r
            for r in await gap_rows(db_session_factory, spec)
            if r["reason"] == "funil_indisponivel"
        ]
        assert len(holes) == 1 and holes[0]["detail"]["open"] is True  # the next process closes it
        assert holes[0]["gap_start"] == T0 + timedelta(seconds=3)
        assert json.dumps(holes[0]["detail"]["rule_set_id"]) == json.dumps(spec.id)


@pytest.mark.asyncio
async def test_a_write_interrupted_by_the_stop_is_handed_back_and_written_not_lost(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leader = addr("A")
    spec = await rule_set(db_engine, leader, addr("B"))
    real = copy_exec_entry.reject_entry
    state = {"calls": 0}

    async def hang_once(*args: Any, **kwargs: Any) -> Any:
        state["calls"] += 1
        if state["calls"] == 1:
            await asyncio.Event().wait()  # the database is slow: the write is in flight at the stop
        return await real(*args, **kwargs)

    monkeypatch.setattr(copy_exec_entry, "reject_entry", hang_once)
    async with running(spec, db_session_factory) as rig:
        ref = leader_ref(buy(leader, mint_address(), at=T0), "regra")
        rig.lane.submit(RejectEntry(mint_address(), ref, "nao_primeira", T0))
        for _ in range(100):
            if state["calls"]:
                break
            await asyncio.sleep(0.02)
        await rig.lane.stop()  # cancels the hanging write, hands it back, writes it
        assert [p["status"] for p in await proposals(db_session_factory, spec)] == ["rejected"]
        holes = [
            r
            for r in await gap_rows(db_session_factory, spec)
            if r["reason"] == "funil_indisponivel"
        ]
        assert holes == []


@pytest.mark.asyncio
async def test_when_the_stop_cannot_record_its_loss_the_final_marker_is_not_written(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leader = addr("A")
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.lane._alive_from = T0  # pyright: ignore[reportPrivateUsage]

        async def count() -> int:
            rows = await gap_rows(db_session_factory, spec)
            return len([r for r in rows if r["reason"] == "lane_alive"])

        before = await count()
        for name in ("reject_entry", "record_gap"):  # the database refuses everything at the stop
            monkeypatch.setattr(
                copy_exec_entry, name, _flaky(getattr(copy_exec_entry, name), 10_000)[0]
            )
        ref = leader_ref(buy(leader, mint_address(), at=T0), "regra")
        rig.lane.outbox.append(RejectEntry(mint_address(), ref, "nao_primeira", T0))
        await rig.lane.stop()
        assert await count() == before  # the marker did not advance past a fact that was lost


@pytest.mark.asyncio
async def test_the_liveness_marker_never_moves_past_a_fact_that_is_not_durable_yet(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R2 round 4 (MF4): a rejected first buy stuck in a retry loop is only in memory; a crash would leave
    a downtime that began AFTER it. The marker stops at the oldest fact still owed."""
    leader = addr("A")
    spec = await rule_set(db_engine, leader, addr("B"))
    monkeypatch.setattr(
        copy_exec_entry, "record_gap", _flaky(copy_exec_entry.record_gap, 10_000)[0]
    )
    stuck_at = T0 + timedelta(seconds=5)
    async with running(spec, db_session_factory) as rig:
        rig.lane._alive_from = T0  # pyright: ignore[reportPrivateUsage]
        rig.clock.advance(seconds=10)
        rig.lane.on_item(gap(stuck_at, None, wallet=leader, reason="nats_silent"))
        await rig.settle()  # the retries are spent; the hole record is still owed
        rig.clock.advance(seconds=60)
        await rig.lane.marker_once()
        alive = [r for r in await gap_rows(db_session_factory, spec) if r["reason"] == "lane_alive"]
        assert alive and max(r["gap_end"] for r in alive) == stuck_at  # NOT 60 s later


@pytest.mark.asyncio
async def test_an_unverified_note_the_stop_cannot_write_is_declared_as_a_hole(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        rig.lane.on_item(buy(leader, mint, at=T0))
        await rig.settle()
        position = next(iter(rig.lane.book.open_positions()))
        monkeypatch.setattr(
            copy_exec_facts, "set_copy_fact", _flaky(copy_exec_facts.set_copy_fact, 10_000)[0]
        )
        rig.lane.outbox.append(UnverifiedIntent(position.key, "SIG", "entry", T0))
        await rig.lane.stop()
        holes = [
            r
            for r in await gap_rows(db_session_factory, spec)
            if r["reason"] == "funil_indisponivel"
        ]
        assert holes  # the restart cannot know the copy was flagged: the loss is declared
