"""T4.89 against a real Postgres (testcontainers): every decision the event
lane records — a proposal, a refusal-trail row — leaves the tape it judged in
``meme_decision_tapes`` (off the hot path), and a proposal also carries the
derived block in its own ``reasons``; a capture or a write that fails never
stops the proposal; the retention sweep keeps a proposal's tape longer than
a trail's. Reuses ``test_event_gate_integration.py``'s fixtures.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

import hunter_meme_worker.event_gate_trail as event_gate_trail
from hunter_core.db.session import role_session
from hunter_meme_worker.event_gate_config import GATE_SHADOW
from hunter_meme_worker.event_gate_eval import evaluate_mint, flush_pending_trail

from .test_event_gate_integration import (
    CREATED,
    _lab,
    _patch_holders,
    _prime_state,
    _radar,
    _rt,
    _seed_caches,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from hunter_meme_worker.event_gate_runtime import EventGateRuntime

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"


async def _rows(factory: async_sessionmaker[AsyncSession], sql: str, **params: Any) -> list[Any]:
    async with role_session(factory, db_role=WORKER) as session:
        return list((await session.execute(text(sql), params)).mappings().all())


async def _ready(
    factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    *,
    snipers: int = 1,
    mode: str = "on",
) -> tuple[EventGateRuntime, str, datetime]:
    mint = f"TAPE_{uuid4().hex[:12]}"
    lab = _lab(factory)
    await _seed_caches(factory, engine, mint, lab=lab)
    rt = _rt(_radar(factory), lab, mode=mode)
    as_of = CREATED + timedelta(seconds=130)
    _prime_state(rt, mint, as_of=as_of)
    _patch_holders(monkeypatch, mint, as_of, snipers=snipers)
    return rt, mint, as_of


async def test_a_proposal_carries_the_evidence_and_leaves_its_tape(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rt, mint, as_of = await _ready(db_session_factory, db_engine, monkeypatch)
    await evaluate_mint(rt, mint, as_of)
    [proposal] = await _rows(
        db_session_factory,
        "SELECT id, reasons, features_end_time FROM meme_proposals WHERE mint = :m",
        m=mint,
    )
    block = proposal["reasons"][-1]
    assert block["feature"] == "decision_tape" and block["used_by_gate"] is False
    assert block["as_of"] == as_of.isoformat()
    assert block["windows"]["60s"]["buys"] == 10 and block["windows"]["60s"]["sells"] == 5
    assert rt.tapes.pending == 1  # offered, not written: the decision never waited on it
    assert (
        await _rows(db_session_factory, "SELECT 1 FROM meme_decision_tapes WHERE mint = :m", m=mint)
        == []
    )
    await flush_pending_trail(rt, as_of + timedelta(seconds=61))  # nothing left to add a tape
    assert await rt.tapes.flush(db_session_factory) == 1
    [tape] = await _rows(
        db_session_factory,
        "SELECT as_of, proposal_ids, trades, trades_in_window, derived "
        "FROM meme_decision_tapes WHERE mint = :m",
        m=mint,
    )
    assert tape["as_of"] == proposal["features_end_time"] == as_of
    assert [str(p) for p in tape["proposal_ids"]] == [str(proposal["id"])]
    assert tape["trades_in_window"] == 15 and len(tape["trades"]) == 15
    assert tape["derived"]["windows"] == block["windows"]
    assert {t["side"] for t in tape["trades"]} == {"buy", "sell"}


async def test_a_near_miss_leaves_one_tape_when_its_trail_row_is_written(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rt, mint, as_of = await _ready(db_session_factory, db_engine, monkeypatch, snipers=3)
    await evaluate_mint(rt, mint, as_of)
    assert rt.tapes.pending == 0  # queued with its trail candidate, not offered yet
    later = as_of + timedelta(milliseconds=300)  # a newer evaluation replaces both
    _prime_state(rt, mint, as_of=later)
    _patch_holders(monkeypatch, mint, later, snipers=3)
    await evaluate_mint(rt, mint, later)
    await flush_pending_trail(rt, later + timedelta(seconds=1))
    assert rt.tapes.pending == 1
    await rt.tapes.flush(db_session_factory)
    joined = await _rows(
        db_session_factory,
        "SELECT t.as_of, t.proposal_ids, r.refusal FROM meme_decision_tapes t "
        "JOIN meme_gate_refusals_by_mint r ON r.mint = t.mint AND r.as_of = t.as_of "
        "WHERE t.mint = :m",
        m=mint,
    )
    assert [(row["as_of"], list(row["proposal_ids"]), row["refusal"]) for row in joined] == [
        (later, [], "snipers_above_max")
    ]


async def test_shadow_records_no_tape(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rt, mint, as_of = await _ready(db_session_factory, db_engine, monkeypatch, mode=GATE_SHADOW)
    await evaluate_mint(rt, mint, as_of)
    assert rt.tapes.offered == 0 and rt.pending_tapes == {}


async def test_a_capture_that_raises_never_stops_the_proposal(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise ArithmeticError("a bug in the snapshot")

    monkeypatch.setattr(event_gate_trail, "capture_decision_tape", boom)
    rt, mint, as_of = await _ready(db_session_factory, db_engine, monkeypatch)
    await evaluate_mint(rt, mint, as_of)
    [proposal] = await _rows(
        db_session_factory, "SELECT reasons FROM meme_proposals WHERE mint = :m", m=mint
    )
    assert all(r.get("feature") != "decision_tape" for r in proposal["reasons"])
    assert rt.tapes.capture_failed == 1 and rt.tapes.pending == 0
    assert rt.stats.proposals_total == 1


async def test_a_failing_tape_write_never_touches_the_proposal(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rt, mint, as_of = await _ready(db_session_factory, db_engine, monkeypatch)
    await evaluate_mint(rt, mint, as_of)

    class _Down:
        async def __aenter__(self) -> Any:
            raise ConnectionError("database unreachable")

        async def __aexit__(self, *exc: object) -> bool:
            return False

    assert await rt.tapes.flush(lambda: _Down()) == 0  # type: ignore[arg-type,return-value]
    assert rt.tapes.failed == 1
    assert (
        len(await _rows(db_session_factory, "SELECT 1 FROM meme_proposals WHERE mint = :m", m=mint))
        == 1
    )


async def test_retention_keeps_a_proposal_tape_longer_than_a_trail_tape(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    now = datetime(2026, 12, 31, 12, 0, tzinfo=UTC)
    insert = (
        "INSERT INTO meme_decision_tapes (mint, as_of, series, proposal_ids, trades, "
        "  trades_in_window, derived) VALUES (:mint, :as_of, 'meme_event_gate_v1', "
        "  CAST(:ids AS uuid[]), '[]'::jsonb, 0, CAST(:derived AS jsonb))"
    )
    tag = uuid4().hex[:8]
    cases: dict[str, tuple[datetime, list[UUID]]] = {
        f"trail8d_{tag}": (now - timedelta(days=8), []),
        f"trail6d_{tag}": (now - timedelta(days=6), []),
        f"prop8d_{tag}": (now - timedelta(days=8), [uuid4()]),
        f"prop91d_{tag}": (now - timedelta(days=91), [uuid4()]),
    }
    async with role_session(db_session_factory, db_role=WORKER) as session:
        for mint, (as_of, ids) in cases.items():
            await session.execute(
                text(insert), {"mint": mint, "as_of": as_of, "ids": ids, "derived": json.dumps({})}
            )
    rt = _rt(_radar(db_session_factory), _lab(db_session_factory))
    await rt.tapes.maybe_prune(db_session_factory, now)
    left = {
        row["mint"]
        for row in await _rows(
            db_session_factory,
            "SELECT mint FROM meme_decision_tapes WHERE mint LIKE :t",
            t=f"%{tag}",
        )
    }
    assert left == {f"trail6d_{tag}", f"prop8d_{tag}"}
    assert rt.tapes.last_prune_day == now.date()


async def test_a_trail_flush_during_the_proposal_insert_never_unlinks_its_tape(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """database-architect review (MEDIUM): the evaluation parks its tape with
    its trail candidate before the first ``await``; the 15 s trail flush that
    runs while the proposal insert awaits must leave that mint alone, or it
    offers the tape unlinked first and ``ON CONFLICT DO NOTHING`` keeps it —
    a proposal's tape stored without its id, pruned at 7 d instead of 90 d."""
    import hunter_meme_worker.event_gate_eval as event_gate_eval

    rt, mint, as_of = await _ready(db_session_factory, db_engine, monkeypatch)
    real_insert = event_gate_eval.insert_proposals_reserved

    async def racing_insert(*args: Any, **kwargs: Any) -> int:
        await flush_pending_trail(rt, as_of + timedelta(seconds=1))
        return await real_insert(*args, **kwargs)

    monkeypatch.setattr(event_gate_eval, "insert_proposals_reserved", racing_insert)
    await evaluate_mint(rt, mint, as_of)
    await rt.tapes.flush(db_session_factory)
    [proposal] = await _rows(
        db_session_factory, "SELECT id FROM meme_proposals WHERE mint = :m", m=mint
    )
    [tape] = await _rows(
        db_session_factory, "SELECT proposal_ids FROM meme_decision_tapes WHERE mint = :m", m=mint
    )
    assert [str(p) for p in tape["proposal_ids"]] == [str(proposal["id"])]
    trail = await _rows(
        db_session_factory,
        "SELECT refusal FROM meme_gate_refusals_by_mint WHERE mint = :m AND as_of = :a",
        m=mint,
        a=as_of,
    )
    assert [row["refusal"] for row in trail] == [None]  # the trail row still landed, once
    assert rt.proposing == set()  # cleared in ``finally``


async def test_the_kill_switch_skips_capture_and_write_and_keeps_the_proposal(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    rt, mint, as_of = await _ready(db_session_factory, db_engine, monkeypatch)
    rt.config = replace(rt.config, decision_tape=False)
    await evaluate_mint(rt, mint, as_of)
    [proposal] = await _rows(
        db_session_factory, "SELECT reasons FROM meme_proposals WHERE mint = :m", m=mint
    )
    assert all(r.get("feature") != "decision_tape" for r in proposal["reasons"])
    assert rt.tapes.offered == 0 and rt.pending_tapes == {}
