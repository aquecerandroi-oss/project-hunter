"""The copy lanes as the worker runs them (H-037), against a real Postgres: the fleet opens ONE source for
the union of the wallets of every active ``clock = 'copy'`` set, routes each item to the lanes that follow
that wallet, and each lane decides, prices after the declared latency, persists and publishes its own
heartbeat; a source that ends is a loss of coverage; without an active set the supervisor is inert.
Labeled fakes; paper only."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_exchanges.pumpfun.solana_codec import b58encode
from hunter_meme_worker.copy_events import Job
from hunter_meme_worker.copy_forever import CopyFleet
from hunter_meme_worker.copy_lane import CopyLane
from hunter_meme_worker.copy_spec import CopySpec
from hunter_meme_worker.copy_wiring import start_copy_lane

from .copy_fakes import Curve, FakeChain, FakeClock
from .copy_rig import retire_copy_sets
from .copy_support import PARAMS, T0, buy, gap

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"


def _addr(suffix: str) -> str:
    return b58encode(os.urandom(32))[:43] + suffix


class _RealClock:
    """Chain-side clock for lanes that run on the real one."""

    @property
    def now(self) -> datetime:
        return utcnow()


class _Feed:
    """A labeled fake `LeaderSource`: records what it was asked for, yields its items, ends."""

    def __init__(self, items: list[Any], *, hang: bool = False) -> None:
        self.items = items
        self.hang = hang
        self.asked: list[list[str]] = []

    async def stream(self, wallets: Any) -> Any:
        self.asked.append(list(wallets))
        for item in self.items:
            yield item
        if self.hang:  # a live source does not end
            await asyncio.Event().wait()


async def _insert_set(
    engine: AsyncEngine, name: str, leaders: list[dict[str, str]], **extra: Any
) -> CopySpec:
    rule_set_id = str(uuid4())
    params: dict[str, Any] = {**PARAMS, "exec_latency_s": "0.05", "leaders": leaders, **extra}
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref) "
                "VALUES (:id, :name, :v, 'research_only', CAST(:params AS jsonb), 'test', 'EXP-M28')"
            ),
            {"id": rule_set_id, "name": name, "v": uuid4().hex[:8], "params": json.dumps(params)},
        )
    return CopySpec.from_params(id=rule_set_id, name=name, version="1", params=params)


async def _bet_count(factory: async_sessionmaker[AsyncSession], rule_set_id: str) -> int:
    async with role_session(factory, db_role=WORKER) as session:
        return int(
            await session.scalar(
                text("SELECT count(*) FROM meme_paper_bets WHERE rule_set_id = CAST(:r AS uuid)"),
                {"r": rule_set_id},
            )
            or 0
        )


@pytest.mark.asyncio
async def test_the_fleet_opens_one_source_for_the_union_and_routes_each_wallet_to_its_lanes(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    shared, only_rule, only_everton = _addr("S"), _addr("R"), _addr("E")
    regra = await _insert_set(
        db_engine,
        "copy_v0",
        [{"wallet": shared, "stratum": "regra"}, {"wallet": only_rule, "stratum": "regra"}],
    )
    everton = await _insert_set(
        db_engine,
        "copy_everton_v0",
        [
            {"wallet": shared, "stratum": "escolha_everton"},
            {"wallet": only_everton, "stratum": "escolha_everton"},
        ],
    )
    mint, mint_e = b58encode(os.urandom(32)), b58encode(os.urandom(32))
    chain = FakeChain(_RealClock())  # type: ignore[arg-type]
    for m in (mint, mint_e):
        chain.set(m, Curve(), at=datetime(2026, 1, 1, tzinfo=UTC))
    now = utcnow()
    feed = _Feed(
        [
            gap(now - timedelta(seconds=5), now - timedelta(seconds=4), wallet=only_everton),
            buy(shared, mint, at=utcnow(), block_time=utcnow() - timedelta(seconds=1)),
            buy(only_everton, mint_e, at=utcnow(), block_time=utcnow() - timedelta(seconds=1)),
        ],
        hang=True,
    )
    lanes = [
        CopyLane(
            spec=spec,
            session_factory=db_session_factory,
            chain=chain,  # type: ignore[arg-type]
            t0=utcnow() - timedelta(hours=1),
        )
        for spec in (regra, everton)
    ]
    fleet = CopyFleet(lanes, feed)  # type: ignore[arg-type]
    assert fleet.wallets == sorted({shared, only_rule, only_everton})
    runner = asyncio.create_task(fleet.run())
    try:
        for _ in range(400):
            if await _bet_count(db_session_factory, regra.id) and await _bet_count(
                db_session_factory, everton.id
            ):
                break
            await asyncio.sleep(0.05)
        # the shared wallet fed BOTH sets (each with its own rule_set_id); the everton-only wallet
        # fed only the secondary; a gap of one wallet reached only the lanes that follow it
        assert await _bet_count(db_session_factory, regra.id) == 1
        assert await _bet_count(db_session_factory, everton.id) == 2
        assert feed.asked == [sorted({shared, only_rule, only_everton})]  # one source, the union
        assert lanes[0].stats.gaps_seen == 0 and lanes[1].stats.gaps_seen == 1
        primary, secondary = lanes[0].fields(), lanes[1].fields()
        assert primary["copy_entries"] == "1" and primary["copy_rule_set"] == "copy_v0/1"
        assert secondary["copy_copy_everton_v0_entries"] == "2"  # never overwrites the primary's
        assert "copy_entries" not in secondary
    finally:
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_source_that_ends_opens_a_global_gap_and_closing_it_rejects_replayed_buys(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = _addr("A"), b58encode(os.urandom(32))
    spec = await _insert_set(db_engine, "copy_v0", [{"wallet": leader, "stratum": "regra"}])
    clock = FakeClock(T0 + timedelta(seconds=100))
    chain = FakeChain(clock)
    chain.set(mint, Curve())
    lane = CopyLane(
        spec=spec,
        session_factory=db_session_factory,
        chain=chain,  # type: ignore[arg-type]
        clock=clock,
        sleep=clock.sleep,
        t0=T0 - timedelta(hours=1),
    )

    class _Flaky:
        """Ends at once, then speaks again with a buy that happened INSIDE the hole."""

        rounds = 0

        async def stream(self, wallets: Any) -> Any:
            self.rounds += 1
            if self.rounds == 2:
                yield buy(
                    leader,
                    mint,
                    at=T0 + timedelta(seconds=101),
                    block_time=T0 + timedelta(seconds=101),
                )
            if self.rounds >= 3:
                raise asyncio.CancelledError

    async def sleep_then_move(seconds: float) -> None:
        clock.advance(seconds=seconds)

    fleet = CopyFleet([lane], _Flaky(), clock=clock, sleep=sleep_then_move)  # type: ignore[arg-type]
    with pytest.raises(asyncio.CancelledError):
        await fleet.read_source()
    # opened at the loss, closed when the stream spoke again, opened again when it ended again
    assert lane.stats.gaps_seen == 3
    jobs: list[Job] = []
    while not lane.queue.empty():
        jobs.append(lane.queue.get_nowait())
    kinds = [type(j).__name__ for j in jobs]
    assert "OpenIntent" not in kinds and "RecordGap" in kinds  # the closed hole is persisted
    assert any(getattr(j, "reason", None) == "lacuna" for j in jobs)  # a buy inside it: lacuna


@pytest.mark.asyncio
async def test_without_an_active_copy_rule_set_the_lane_publishes_inert_and_opens_nothing(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await retire_copy_sets(db_engine)
    beats: list[dict[str, str]] = []

    async def heartbeat(fields: dict[str, str]) -> None:
        beats.append(fields)

    feed = _Feed([])
    runner = asyncio.create_task(
        start_copy_lane(
            session_factory=db_session_factory,
            chain=FakeChain(FakeClock()),  # type: ignore[arg-type]
            source=feed,  # type: ignore[arg-type]
            heartbeat=heartbeat,
        )
    )
    try:
        for _ in range(200):
            if beats:
                break
            await asyncio.sleep(0.05)
        assert beats and beats[0]["copy_state"] == "inert" and beats[0]["copy_leaders"] == "0"
        assert feed.asked == []  # the source was never even opened
    finally:
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)


@pytest.mark.asyncio
async def test_the_fleet_recovers_every_lane_before_it_opens_the_source(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader = _addr("A")
    spec = await _insert_set(db_engine, "copy_v0", [{"wallet": leader, "stratum": "regra"}])
    lane = CopyLane(
        spec=spec,
        session_factory=db_session_factory,
        chain=FakeChain(_RealClock()),  # type: ignore[arg-type]
        t0=utcnow() - timedelta(hours=1),
    )
    order: list[str] = []
    recover = lane.start

    async def slow_start() -> None:
        order.append("recovering")
        await asyncio.sleep(0.3)  # a slow funnel query: the source must not open meanwhile
        await recover()
        order.append("recovered")

    lane.start = slow_start  # type: ignore[method-assign]

    class _Probe:
        async def stream(self, wallets: Any) -> Any:
            order.append("source_opened")
            await asyncio.Event().wait()
            yield  # pragma: no cover

    runner = asyncio.create_task(CopyFleet([lane], _Probe()).run())  # type: ignore[arg-type]
    try:
        for _ in range(100):
            if "source_opened" in order:
                break
            await asyncio.sleep(0.05)
        assert order == ["recovering", "recovered", "source_opened"]
    finally:
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)
