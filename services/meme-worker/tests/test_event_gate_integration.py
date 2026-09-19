"""T4.52b-3 against a real Postgres (testcontainers): the event gate proposes
through ``flow_v2/1`` exactly like the 15-second lane, but from the
in-memory series a chain event feeds — one row, ``series = meme_event_gate_v1``,
one wake. Run alone (``timeout 590``): shares the container fixture of
``conftest.py``.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
import websockets
from sqlalchemy import text

import hunter_meme_worker.event_gate_eval as event_gate_eval
from hunter_core.db.session import role_session
from hunter_exchanges.pumpfun.rpc_ws import SolanaWsClient
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.event_gate import _read_loop
from hunter_meme_worker.event_gate_caches import EventGateCaches
from hunter_meme_worker.event_gate_config import GATE_ON, GATE_SHADOW, EventGateConfig
from hunter_meme_worker.event_gate_eval import evaluate_mint, flush_pending_trail
from hunter_meme_worker.event_gate_rows import EventReserves
from hunter_meme_worker.event_gate_runtime import EventGateRuntime
from hunter_meme_worker.event_state import CurvePoint, TapeTrade
from hunter_meme_worker.features_tape import HoldersObservation
from hunter_meme_worker.lab import LabContext, LabState
from hunter_meme_worker.lab_fast import fast_gate_step
from hunter_meme_worker.lab_repo import load_active_rule_sets
from hunter_meme_worker.repo import insert_snapshot
from hunter_meme_worker.repo_fast import insert_fast_rows
from hunter_meme_worker.tracker import MintTracker

from .test_lab_fast import _fast_row, _flow_set, _plant_token
from .test_lab_persistence import FakeQuotes, Heartbeats, _snapshot
from .test_lab_wake import Waker

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
CREATED = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
INITIAL_REAL_TOKEN = Decimal("793100000")
TOTAL_SUPPLY = Decimal("1000000000")


def _radar(factory: async_sessionmaker[AsyncSession]) -> RadarContext:
    return RadarContext(
        config=MemeConfig(enabled=True),
        session_factory=factory,
        tracker=MintTracker(window_minutes=1440, cap=200),
        state=RadarState(),
        events=None,  # type: ignore[arg-type]
        curves=None,  # type: ignore[arg-type]
        chain=None,  # type: ignore[arg-type]
    )


def _lab(factory: async_sessionmaker[AsyncSession], *, wake: Any = None) -> LabContext:
    return LabContext(
        config=MemeConfig(enabled=True, lab_enabled=True),
        session_factory=factory,
        state=LabState(),
        quotes=FakeQuotes(),
        heartbeat=Heartbeats(),
        wake=wake,
        caches=EventGateCaches(),
    )


async def _seed_caches(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine, mint: str, *, lab: LabContext
) -> str:
    """Plant the token, a copy of ``flow_v2/1`` and one early 15-second row too
    young to satisfy the gate itself — just enough for ``fast_gate_step`` to
    cache the base row, the rule set and the (empty) pedigree, exactly as a
    real Lab tick would before any event ever reaches this mint."""
    rule_set = await _flow_set(engine)
    await _plant_token(
        factory, mint, created_at=CREATED, creator=f"C_{mint}", symbol=f"S{mint[-6:]}"
    )
    photo = CREATED + timedelta(seconds=10)
    async with role_session(factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, photo, "34", "946000000"))
        await insert_fast_rows(session, [_fast_row(mint, photo + timedelta(seconds=1), photo)])
    async with role_session(factory, db_role=WORKER) as session:
        specs = [s for s in await load_active_rule_sets(session) if s.id == rule_set]
    _rows, proposals = await fast_gate_step(lab, specs, {}, now=photo + timedelta(seconds=2))
    assert proposals == 0  # the seed row is too young (min_age_s = 30) - no proposal yet
    assert lab.caches is not None and mint in lab.caches.base_rows
    return rule_set


def _holders_pair(as_of: datetime, *, snipers: int = 1) -> list[HoldersObservation]:
    return [
        HoldersObservation(
            observed_at=as_of - timedelta(seconds=90),
            received_at=as_of - timedelta(seconds=89),
            source="trenches_new",
            holders=9,
            top10_share=Decimal("0.2"),
            dev_share=Decimal("0.05"),
            snipers=snipers,
        ),
        HoldersObservation(
            observed_at=as_of - timedelta(seconds=10),
            received_at=as_of - timedelta(seconds=9),
            source="trenches_new",
            holders=12,
            top10_share=Decimal("0.2"),
            dev_share=Decimal("0.05"),
            snipers=snipers,
        ),
    ]


def _prime_state(rt: EventGateRuntime, mint: str, *, as_of: datetime) -> None:
    """Everything ``build_event_row`` needs to satisfy ``flow_v2/1``, written
    straight into the mint's in-memory state — bypassing the WS decode
    pipeline (already proven against the T4.52b-1 fixtures elsewhere) so this
    test is about the gate, not the transport."""
    covered_since = as_of - timedelta(seconds=90)
    state = rt.book.touch(mint, at=covered_since, first_seen_at=covered_since)
    assert state is not None
    state.covered_since = covered_since
    state.total_supply = TOTAL_SUPPLY
    state.creator = f"C_{mint}"
    state.complete = False
    state.mayhem = False
    state.points.append(
        CurvePoint(
            observed_at=as_of - timedelta(seconds=90),
            received_at=as_of - timedelta(seconds=89),
            mcap_sol=Decimal("30"),
            real_sol=Decimal("29"),
            real_token=INITIAL_REAL_TOKEN * Decimal("0.97"),
            mayhem=False,
        )
    )
    state.points.append(
        CurvePoint(
            observed_at=as_of,
            received_at=as_of,
            mcap_sol=Decimal("34"),
            real_sol=Decimal("33"),
            real_token=INITIAL_REAL_TOKEN * Decimal("0.90"),
            mayhem=False,
        )
    )
    trade_at = as_of - timedelta(seconds=30)
    for i in range(10):
        state.trades.append(
            TapeTrade(
                block_time=trade_at,
                received_at=trade_at,
                trader=f"BUYER_{mint}_{i}",
                side="buy",
                sol_lamports=2_000_000_000,
            )
        )
    for i in range(5):
        state.trades.append(
            TapeTrade(
                block_time=trade_at,
                received_at=trade_at,
                trader=f"SELLER_{mint}_{i}",
                side="sell",
                sol_lamports=1_000_000_000,
            )
        )
    rt.reserves[mint] = EventReserves(Decimal("60"), INITIAL_REAL_TOKEN * Decimal("1.10"))


def _patch_holders(
    monkeypatch: pytest.MonkeyPatch, mint: str, as_of: datetime, *, snipers: int = 1
) -> None:
    """Stand in for ``ctx.boards``/``ctx.risk`` (neither wired in this test's
    minimal ``RadarContext``) with the two readings ``flow_v2/1`` needs.
    ``snipers=3`` (``max_snipers`` is 2) turns this into a near-miss: exactly
    one refusal, everything else about the row still satisfies the gate."""

    def fake(radar: RadarContext, m: str) -> list[HoldersObservation]:
        return _holders_pair(as_of, snipers=snipers) if m == mint else []

    monkeypatch.setattr(event_gate_eval, "_holders_readings", fake)


def _rt(
    radar: RadarContext, lab: LabContext, *, mode: str = GATE_ON, ws: Any = None
) -> EventGateRuntime:
    config = EventGateConfig(mode=mode, ws_url="ws://x", commitment="confirmed", max_mints=150)
    return EventGateRuntime(radar=radar, lab=lab, ws=ws, config=config)  # type: ignore[arg-type]


async def _proposal_count(factory: async_sessionmaker[AsyncSession], mint: str) -> int:
    async with role_session(factory, db_role=WORKER) as session:
        return int(
            (
                await session.execute(
                    text("SELECT count(*) FROM meme_proposals WHERE mint = :m"), {"m": mint}
                )
            ).scalar_one()
        )


async def _trail_count(factory: async_sessionmaker[AsyncSession], mint: str) -> int:
    async with role_session(factory, db_role=WORKER) as session:
        return int(
            (
                await session.execute(
                    text("SELECT count(*) FROM meme_gate_refusals_by_mint WHERE mint = :m"),
                    {"m": mint},
                )
            ).scalar_one()
        )


async def test_an_event_that_passes_flow_v2_becomes_one_proposal(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mint = f"EVT_{uuid4().hex[:12]}"
    waker = Waker()
    lab = _lab(db_session_factory, wake=waker)
    await _seed_caches(db_session_factory, db_engine, mint, lab=lab)
    rt = _rt(_radar(db_session_factory), lab)
    as_of = CREATED + timedelta(seconds=130)
    _prime_state(rt, mint, as_of=as_of)
    _patch_holders(monkeypatch, mint, as_of)
    await evaluate_mint(rt, mint, as_of)
    assert await _proposal_count(db_session_factory, mint) == 1
    assert waker.calls == 1
    async with role_session(db_session_factory, db_role=WORKER) as session:
        row = (
            (
                await session.execute(
                    text("SELECT reasons, status, decided_by FROM meme_proposals WHERE mint = :m"),
                    {"m": mint},
                )
            )
            .mappings()
            .one()
        )
    assert row["reasons"][0]["series"] == "meme_event_gate_v1"
    assert row["status"] == "approved" and row["decided_by"] == "rules"

    # Double replay at the same instant: the DB's own unique index dedupes.
    await evaluate_mint(rt, mint, as_of)
    assert await _proposal_count(db_session_factory, mint) == 1


async def test_already_open_via_recently_proposed_skips_the_second_lane(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mint = f"EVT_{uuid4().hex[:12]}"
    lab = _lab(db_session_factory)
    rule_set = await _seed_caches(db_session_factory, db_engine, mint, lab=lab)
    rt = _rt(_radar(db_session_factory), lab)
    as_of = CREATED + timedelta(seconds=130)
    _prime_state(rt, mint, as_of=as_of)
    _patch_holders(monkeypatch, mint, as_of)
    assert lab.caches is not None
    lab.caches.mark_proposed(mint, rule_set, now=as_of, ttl_s=120)  # the fast lane proposed first
    await evaluate_mint(rt, mint, as_of)
    assert await _proposal_count(db_session_factory, mint) == 0


async def test_shadow_mode_counts_and_never_inserts(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mint = f"EVT_{uuid4().hex[:12]}"
    lab = _lab(db_session_factory)
    await _seed_caches(db_session_factory, db_engine, mint, lab=lab)
    rt = _rt(_radar(db_session_factory), lab, mode=GATE_SHADOW)
    as_of = CREATED + timedelta(seconds=130)
    _prime_state(rt, mint, as_of=as_of)
    _patch_holders(monkeypatch, mint, as_of)
    await evaluate_mint(rt, mint, as_of)
    assert await _proposal_count(db_session_factory, mint) == 0
    assert rt.stats.shadow_proposals_total == 1
    assert rt.stats.proposals_total == 0


async def test_shadow_mode_writes_no_refusal_trail_even_for_a_near_miss(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F6/F7: ``shadow`` never opens ``role_session`` at all — a near-miss
    (exactly one refusal, ``snipers_above_max``) that would have queued a
    trail candidate in ``on`` leaves no row here."""
    mint = f"EVT_{uuid4().hex[:12]}"
    lab = _lab(db_session_factory)
    await _seed_caches(db_session_factory, db_engine, mint, lab=lab)
    baseline = await _trail_count(db_session_factory, mint)  # the seed's own too-young near-miss
    rt = _rt(_radar(db_session_factory), lab, mode=GATE_SHADOW)
    as_of = CREATED + timedelta(seconds=130)
    _prime_state(rt, mint, as_of=as_of)
    _patch_holders(monkeypatch, mint, as_of, snipers=3)  # max_snipers is 2
    await evaluate_mint(rt, mint, as_of)
    assert await _proposal_count(db_session_factory, mint) == 0
    assert await _trail_count(db_session_factory, mint) == baseline  # unchanged: no session at all
    assert rt.pending_trail == {}


async def test_on_mode_batches_the_refusal_trail_not_per_evaluation(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F6/F7: a near-miss with no proposal to insert must not open a session
    of its own — it is queued and only written by the periodic flush."""
    mint = f"EVT_{uuid4().hex[:12]}"
    lab = _lab(db_session_factory)
    await _seed_caches(db_session_factory, db_engine, mint, lab=lab)
    baseline = await _trail_count(db_session_factory, mint)  # the seed's own too-young near-miss
    rt = _rt(_radar(db_session_factory), lab)  # GATE_ON
    as_of = CREATED + timedelta(seconds=130)
    _prime_state(rt, mint, as_of=as_of)
    _patch_holders(monkeypatch, mint, as_of, snipers=3)  # max_snipers is 2
    await evaluate_mint(rt, mint, as_of)
    assert await _proposal_count(db_session_factory, mint) == 0  # refused, nothing to insert
    assert await _trail_count(db_session_factory, mint) == baseline  # F6: not written yet
    assert mint in rt.pending_trail
    await flush_pending_trail(rt, as_of + timedelta(seconds=1))
    assert (
        await _trail_count(db_session_factory, mint) == baseline + 1
    )  # the periodic flush wrote it
    assert mint not in rt.pending_trail

    # Immediately after: the 60-second per-mint cooldown holds even if a new
    # near-miss is queued right away — no flood (F7).
    later = as_of + timedelta(seconds=2)
    _prime_state(rt, mint, as_of=later)
    _patch_holders(monkeypatch, mint, later, snipers=3)
    await evaluate_mint(rt, mint, later)
    await flush_pending_trail(rt, later + timedelta(seconds=1))
    assert await _trail_count(db_session_factory, mint) == baseline + 1  # still just the one


async def test_fast_gate_step_in_the_same_instant_makes_already_open(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A proposal the 15-second lane just wrote (in the same Lab tick that
    refreshed the caches) must stop the event gate from proposing the same
    mint again — ``already_open`` from the durable read, not only the
    in-memory guard."""
    mint = f"EVT_{uuid4().hex[:12]}"
    lab = _lab(db_session_factory)
    rule_set = await _seed_caches(db_session_factory, db_engine, mint, lab=lab)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        specs = [s for s in await load_active_rule_sets(session) if s.id == rule_set]
    # Plant a proposal by hand, the same durable fact ``open_mints_for`` reads.
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await session.execute(
            text(
                "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
                "  expires_at, features_end_time, quote, reasons, suggested, decision, decided_by, "
                "  decided_at) "
                "VALUES (gen_random_uuid(), :mint, CAST(:rs AS uuid), 'rules', 'approved', now(), "
                "  now() + interval '2 minutes', now(), '{}'::jsonb, '[]'::jsonb, '{}'::jsonb, "
                "  '{}'::jsonb, 'rules', now())"
            ),
            {"mint": mint, "rs": rule_set},
        )
    # A fresh 15-second row so this tick's ``fast_gate_step`` does not bail out
    # early with nothing to fold (its own guard against an idle window) —
    # ``open_mints``/``base_rows`` only refresh when it has rows to judge.
    photo2 = CREATED + timedelta(seconds=190)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, photo2, "40", "930000000"))
        await insert_fast_rows(session, [_fast_row(mint, photo2 + timedelta(seconds=1), photo2)])
    # A fresh fast_gate_step tick refreshes ``open_mints`` wholesale from the DB.
    await fast_gate_step(lab, specs, {}, now=CREATED + timedelta(seconds=200))
    rt = _rt(_radar(db_session_factory), lab)
    as_of = CREATED + timedelta(seconds=210)
    _prime_state(rt, mint, as_of=as_of)
    _patch_holders(monkeypatch, mint, as_of)
    await evaluate_mint(rt, mint, as_of)
    assert await _proposal_count(db_session_factory, mint) == 1  # the hand-planted one, no second


async def test_no_base_row_is_counted_and_never_evaluated(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    seeded = f"EVT_{uuid4().hex[:12]}"
    lab = _lab(db_session_factory)
    await _seed_caches(db_session_factory, db_engine, seeded, lab=lab)  # populates caches.specs
    rt = _rt(_radar(db_session_factory), lab)
    unseen = f"EVT_{uuid4().hex[:12]}"
    as_of = CREATED + timedelta(seconds=130)
    rt.book.touch(unseen, at=as_of, first_seen_at=as_of)
    await evaluate_mint(rt, unseen, as_of)
    assert rt.stats.no_base_row_total == 1
    assert rt.stats.evaluations_total == 0


# ---- reconnect: a real in-process WS server, dropped once -------------------------


async def _serve_drop_once(connections: list[int]) -> Any:
    async def handler(ws: Any) -> None:
        connections.append(1)
        is_first = len(connections) == 1
        async for raw in ws:
            request = json.loads(raw)
            sub_id = 9000 + len(connections)
            await ws.send(json.dumps({"jsonrpc": "2.0", "result": sub_id, "id": request["id"]}))
            slot = 1 if is_first else 2
            await ws.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "slotNotification",
                        "params": {
                            "result": {"slot": slot, "parent": slot - 1, "root": 0},
                            "subscription": sub_id,
                        },
                    }
                )
            )
            if is_first:
                await asyncio.sleep(0.05)
                return  # drop right after the first response

    return await websockets.serve(handler, "127.0.0.1", 0)


async def test_reconnect_writes_a_gap_row_and_resets_the_tape(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    connections: list[int] = []
    server = await _serve_drop_once(connections)
    rt: EventGateRuntime | None = None
    state = None
    try:
        port = server.sockets[0].getsockname()[1]

        async def _fast_sleep(_delay: float) -> None:
            await asyncio.sleep(0)

        client = SolanaWsClient(
            url=f"ws://127.0.0.1:{port}", sleep=_fast_sleep, rand=lambda: 0.0, connect_timeout_s=5.0
        )
        lab = _lab(db_session_factory)
        rt = EventGateRuntime(
            radar=_radar(db_session_factory),
            lab=lab,
            ws=client,  # type: ignore[arg-type]
            config=EventGateConfig(
                mode=GATE_ON, ws_url="ws://x", commitment="confirmed", max_mints=150
            ),
        )
        mint = f"EVT_{uuid4().hex[:12]}"
        state = rt.book.touch(mint, at=datetime.now(UTC), first_seen_at=datetime.now(UTC))
        assert state is not None
        state.trades.append(
            TapeTrade(
                block_time=datetime.now(UTC),
                received_at=datetime.now(UTC),
                trader="X",
                side="buy",
                sol_lamports=1,
            )
        )
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=100)
        task = asyncio.create_task(_read_loop(rt, queue))
        await client.subscribe_slot()
        row = None
        for _ in range(200):
            if rt.stats.reconnects >= 1:
                # The gap row is the durable side effect: wait for *it*, not a
                # fixed delay, before cancelling the loop mid-write.
                async with role_session(db_session_factory, db_role=WORKER) as session:
                    row = (
                        (
                            await session.execute(
                                text(
                                    "SELECT stream FROM meme_ingest_gaps WHERE stream = 'solana_ws' "
                                    "ORDER BY gap_start DESC LIMIT 1"
                                )
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                if row is not None:
                    break
            await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await client.aclose()
    finally:
        server.close()
        await server.wait_closed()

    assert rt is not None and state is not None
    assert rt.stats.reconnects == 1
    assert state.gaps == 1
    assert len(state.trades) == 0  # mark_gap clears the tape - it warms again
    assert row is not None and row["stream"] == "solana_ws"
