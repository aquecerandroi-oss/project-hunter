"""T4.91 review fixes against a real Postgres (risk-engine-guardian and
database-architect, 24/09/2026):

- a slow insert of the arm never delays the next frame on the shared
  evaluation loop (the insert runs in ``rt.pullback_inserts``);
- ``operator/5`` and ``recuo_v1/1`` approving the same mint at the same
  instant: the desk's stored proposal is identical to a run with no arm;
- the arm's open paper bets never pin a mint in the tracker — a pin would
  keep folding ``meme_features_1m`` rows (``creator_sold`` among them) that
  the desk's pedigree reads, and would narrow the tracker's cap for everyone.

Run alone (``timeout 590``).
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import hunter_meme_worker.event_gate as event_gate
import hunter_meme_worker.event_gate_pullback as event_gate_pullback
from hunter_core.db.session import role_session
from hunter_exchanges.pumpfun.rpc_ws_models import LogsNotification
from hunter_meme_worker.entry_pullback import PULLBACK_ARM_RULE_SET_ID
from hunter_meme_worker.event_gate_eval import evaluate_mint
from hunter_meme_worker.lab_repo import load_active_rule_sets
from hunter_meme_worker.tracker_pins import pinned_mints

from .test_event_gate_integration import (
    WORKER,
    _lab,
    _patch_holders,
    _prime_state,
    _proposal_count,
    _radar,
    _rt,
    _seed_caches,
)
from .test_event_gate_pullback_integration import T0, _armed, _stub_decode, _trade
from .test_lab_fast import _flow_set

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

pytestmark = pytest.mark.integration

PULLBACK_PARAMS = '{"entry_pullback_pct": "5", "entry_pullback_window_s": 60}'


def _notification(sub_id: int, key: str, received_at: Any) -> LogsNotification:
    return LogsNotification(
        subscription_id=sub_id,
        kind="logs",
        slot=9000,
        signature=f"sig-{key}",
        err=None,
        logs=(key,),
        received_at=received_at,
    )


async def test_a_slow_insert_never_delays_the_next_frame(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mint, _rule_set, rt = await _armed(db_session_factory, db_engine, monkeypatch)
    other = f"OTHER_{uuid4().hex[:8]}"
    rt.book.touch(other, at=T0, first_seen_at=T0)
    dip = _trade(mint, "dip", s=12, ratio="0.90")
    tick = _trade(other, "tick", s=12.5, ratio="1")
    _stub_decode(monkeypatch, {"dip": dip, "tick": tick})
    rt.subs_by_logical.update({77: mint, 78: other})
    decided = T0 + timedelta(seconds=13)
    monkeypatch.setattr(event_gate, "utcnow", lambda: decided)
    release = asyncio.Event()
    real_insert = event_gate_pullback.insert_proposals_reserved

    async def slow_insert(*args: Any, **kwargs: Any) -> int:
        await release.wait()  # the database hangs on the arm's insert
        return await real_insert(*args, **kwargs)

    monkeypatch.setattr(event_gate_pullback, "insert_proposals_reserved", slow_insert)
    queue: asyncio.Queue[Any] = asyncio.Queue()
    queue.put_nowait(_notification(77, "dip", dip.received_at))
    queue.put_nowait(_notification(78, "tick", tick.received_at))
    loop = asyncio.create_task(event_gate._evaluate_loop(rt, queue))
    try:
        async with asyncio.timeout(5):
            while rt.stats.events_total < 2:  # noqa: ASYNC110 - polling a plain counter
                await asyncio.sleep(0.01)
        assert rt.pullback_inserts.in_flight == 1, "...while the arm's insert still hangs"
        assert await _proposal_count(db_session_factory, mint) == 0
        release.set()
        await rt.pullback_inserts.join()
    finally:
        loop.cancel()
        await asyncio.gather(loop, return_exceptions=True)
    assert await _proposal_count(db_session_factory, mint) == 1
    assert rt.pullback.proposed == 1


async def _desk_proposal(factory: async_sessionmaker[AsyncSession], rule_set: str) -> Any:
    async with role_session(factory, db_role=WORKER) as session:
        return (
            (
                await session.execute(
                    text(
                        "SELECT status, proposed_at, expires_at, features_end_time, quote, "
                        "  reasons, suggested, decision, decided_by, decided_at "
                        "FROM meme_proposals WHERE rule_set_id = CAST(:rs AS uuid)"
                    ),
                    {"rs": rule_set},
                )
            )
            .mappings()
            .one()
        )


async def test_the_desk_proposes_the_same_row_with_or_without_the_arm_beside_it(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """risk-engine-guardian (LOW): both sets in the cache approve the same mint
    at the same ``now`` — the desk's row (reasons, tape block, quote) is the
    row a run with no arm writes."""
    mint = f"PAIR_{uuid4().hex[:10]}"
    lab = _lab(db_session_factory)
    desk_a = await _seed_caches(db_session_factory, db_engine, mint, lab=lab)
    rt_a = _rt(_radar(db_session_factory), lab)
    _prime_state(rt_a, mint, as_of=T0)
    _patch_holders(monkeypatch, mint, T0)
    await evaluate_mint(rt_a, mint, T0)
    desk_b, arm = await _flow_set(db_engine), await _flow_set(db_engine)
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE meme_rule_sets SET params = params || CAST(:p AS jsonb) WHERE id = :id"),
            {"id": arm, "p": PULLBACK_PARAMS},
        )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        by_id = {s.id: s for s in await load_active_rule_sets(session)}
    assert lab.caches is not None
    lab.caches.specs = (by_id[desk_b], by_id[arm])
    rt_b = _rt(_radar(db_session_factory), lab)
    _prime_state(rt_b, mint, as_of=T0)
    await evaluate_mint(rt_b, mint, T0)
    assert rt_b.pullback.armed == 1, "the arm armed beside the desk"
    alone = dict(await _desk_proposal(db_session_factory, desk_a))
    beside = dict(await _desk_proposal(db_session_factory, desk_b))
    assert beside == alone
    assert any(r.get("feature") == "decision_tape" for r in beside["reasons"])


async def test_the_arms_open_bets_never_pin_a_mint(db_engine: AsyncEngine) -> None:
    """Investigated (guardian's open question): a pinned mint stays tracked
    past the cap, ``fold.fold_minute`` keeps writing its ``meme_features_1m``
    rows — ``creator_sold`` included, the first, un-subtracted source of
    ``lab_repo_fast._PEDIGREE``'s ``creator_prior_dump_count`` — and the cap of
    everyone else narrows by one. So the arm's bets pin nothing; another
    set's open bet on the same kind of mint still does."""
    arm_mint, desk_mint = f"ARMPIN_{uuid4().hex[:8]}", f"DESKPIN_{uuid4().hex[:8]}"
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            for mint, rule_set in (
                (arm_mint, PULLBACK_ARM_RULE_SET_ID),
                (desk_mint, "01994d00-6c1a-7000-8000-000000000011"),
            ):
                proposal = str(uuid4())
                await connection.execute(
                    text(
                        "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, "
                        "  expires_at, decision, decided_by, decided_at) VALUES (:id, :mint, "
                        "  :rs, 'operator', 'approved', now() + interval '2 minutes', "
                        "  '{}'::jsonb, 'user', now())"
                    ),
                    {"id": proposal, "mint": mint, "rs": rule_set},
                )
                await connection.execute(
                    text(
                        "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, "
                        "  entry_at, entry, initial_risk_sol, params) VALUES (:id, :p, :rs, "
                        "  :mint, 'paper', now(), '{}'::jsonb, 0.07, '{}'::jsonb)"
                    ),
                    {"id": str(uuid4()), "p": proposal, "rs": rule_set, "mint": mint},
                )
            session = AsyncSession(bind=connection)
            pinned = await pinned_mints(session, now=T0.replace(year=2000))
            await session.close()
        finally:
            await transaction.rollback()
    assert desk_mint in pinned
    assert arm_mint not in pinned
